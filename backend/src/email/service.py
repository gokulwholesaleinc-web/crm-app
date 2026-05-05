"""Email service layer - handles sending, tracking, and queue management."""

import asyncio
import base64
import html
import logging
import re
from datetime import UTC, datetime, timedelta

import resend  # pyright: ignore[reportMissingImports]
from sqlalchemy import and_, func, literal, or_, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.constants import DEFAULT_PAGE_SIZE
from src.email.branded_templates import TenantBrandingHelper, render_branded_email
from src.email.models import EmailQueue, InboundEmail
from src.email.types import EmailAttachment

logger = logging.getLogger(__name__)


async def _resolve_from_name(db: AsyncSession, user_id: int, fallback_email: str) -> str:
    """Prefer the sender's real name over the Gmail local-part.

    Order: User.full_name → tenant's ``email_from_name`` → local-part of
    the connected Gmail address. The Gmail API always sends from the
    authenticated mailbox regardless of this value, so we only control
    the display-name portion of the From header here.
    """
    from src.auth.models import User

    user = await db.get(User, user_id)
    if user and user.full_name and user.full_name.strip():
        return user.full_name.strip()

    branding = await TenantBrandingHelper.get_branding_for_user(db, user_id)
    tenant_name = (branding.get("email_from_name") or "").strip()
    if tenant_name:
        return tenant_name

    return fallback_email.split("@")[0]


async def _try_gmail_send(
    email: EmailQueue,
    db: AsyncSession,
    *,
    reply_to_email_id: int | None = None,
    reply_to_inbound_id: int | None = None,
    attachments: list[EmailAttachment] | None = None,
) -> bool:
    if not email.sent_by_id:
        return False
    from src.integrations.gmail.models import GmailConnection
    result = await db.execute(
        select(GmailConnection).where(
            GmailConnection.user_id == email.sent_by_id,
            GmailConnection.revoked_at.is_(None),
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        return False

    from src.integrations.gmail.client import GmailClient
    from src.integrations.gmail.sender import build_rfc822

    prior_thread_id, prior_message_id = await _resolve_reply_context(
        db,
        reply_to_email_id=reply_to_email_id,
        reply_to_inbound_id=reply_to_inbound_id,
        entity_type=email.entity_type,
        entity_id=email.entity_id,
        sent_by_id=email.sent_by_id,
    )

    from_name = await _resolve_from_name(db, email.sent_by_id, conn.email)

    raw = build_rfc822(
        to=email.to_email,
        subject=email.subject,
        body_html=email.body,
        body_text=email.body,
        from_email=conn.email,
        from_name=from_name,
        in_reply_to=prior_message_id,
        references=prior_message_id,
        attachments=attachments,
    )

    async with GmailClient(conn, db) as client:
        result = await client.send_message(raw, thread_id=prior_thread_id)

    # Store None, not "", when Gmail omits a field. Empty strings slip past
    # `thread_id IS NOT NULL` filters and poison future thread-context lookups.
    email.message_id = result.get("id") or None
    email.thread_id = result.get("threadId") or None
    email.sent_via = "gmail"
    return True


async def _resolve_reply_context(
    db: AsyncSession,
    *,
    reply_to_email_id: int | None,
    reply_to_inbound_id: int | None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    sent_by_id: int | None = None,
) -> tuple[str | None, str | None]:
    """Resolve thread/message-id to use for In-Reply-To / threadId on a send.

    Prefers the exact email the user clicked Reply on (only one of the two IDs
    is used per send). Falls back to the newest message-bearing row on the
    entity so replies still thread when no explicit target was supplied.

    Reply targets are scoped to the outgoing email's entity so a caller can't
    pass an id from another contact/tenant and exfiltrate its thread metadata.
    EmailQueue targets additionally require the sender match, since EmailQueue
    rows are per-user.
    """
    if reply_to_email_id is not None and entity_type and entity_id:
        filters = [
            EmailQueue.id == reply_to_email_id,
            EmailQueue.entity_type == entity_type,
            EmailQueue.entity_id == entity_id,
        ]
        if sent_by_id is not None:
            filters.append(EmailQueue.sent_by_id == sent_by_id)
        row = await db.execute(
            select(EmailQueue.thread_id, EmailQueue.message_id).where(*filters)
        )
        hit = row.first()
        if hit is not None:
            return hit.thread_id, hit.message_id
    if reply_to_inbound_id is not None and entity_type and entity_id:
        row = await db.execute(
            select(InboundEmail.thread_id, InboundEmail.message_id).where(
                InboundEmail.id == reply_to_inbound_id,
                InboundEmail.entity_type == entity_type,
                InboundEmail.entity_id == entity_id,
            )
        )
        hit = row.first()
        if hit is not None:
            return hit.thread_id, hit.message_id
    return await _find_thread_context(db, entity_type, entity_id)


async def _find_thread_context(
    db: AsyncSession,
    entity_type: str | None,
    entity_id: int | None,
) -> tuple[str | None, str | None]:
    """Best-effort thread context for a reply when no specific target was given.

    Returns the most recent message on the entity — inbound or outbound — that
    still has a Message-ID. The Gmail threadId may be None (e.g. older rows
    from before the Gmail integration, or Resend-only sends); callers should
    still use the message_id for In-Reply-To/References so non-Gmail clients
    thread correctly.
    """
    if not entity_type or not entity_id:
        return None, None

    outbound = await db.execute(
        select(
            EmailQueue.thread_id,
            EmailQueue.message_id,
            EmailQueue.created_at.label("ts"),
        )
        .where(
            EmailQueue.entity_type == entity_type,
            EmailQueue.entity_id == entity_id,
            EmailQueue.message_id.isnot(None),
        )
        .order_by(EmailQueue.created_at.desc())
        .limit(1)
    )
    out_row = outbound.first()

    inbound = await db.execute(
        select(
            InboundEmail.thread_id,
            InboundEmail.message_id,
            InboundEmail.received_at.label("ts"),
        )
        .where(
            InboundEmail.entity_type == entity_type,
            InboundEmail.entity_id == entity_id,
            InboundEmail.message_id.isnot(None),
        )
        .order_by(InboundEmail.received_at.desc())
        .limit(1)
    )
    in_row = inbound.first()

    candidates = [r for r in (out_row, in_row) if r is not None]
    if not candidates:
        return None, None
    newest = max(candidates, key=lambda r: r.ts)
    return newest.thread_id, newest.message_id


async def _create_email_activity(
    db: AsyncSession,
    email: EmailQueue,
) -> None:
    if not email.entity_type or not email.entity_id:
        return
    from src.activities.models import Activity, ActivityType
    activity = Activity(
        activity_type=ActivityType.EMAIL.value,
        subject=f"Email sent: {email.subject[:200]}",
        entity_type=email.entity_type,
        entity_id=email.entity_id,
        email_to=email.to_email,
        email_cc=email.cc,
        owner_id=email.sent_by_id,
        is_completed=True,
        completed_at=datetime.now(UTC),
    )
    db.add(activity)
    await db.flush()

MAX_RETRIES = 5


def send_email(
    to_email: str,
    subject: str,
    body: str,
    from_email: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
    attachments: list[EmailAttachment] | None = None,
) -> None:
    """Send an email via Resend. Raises on failure."""
    resend.api_key = settings.RESEND_API_KEY
    payload = {
        "from": from_email or settings.EMAIL_FROM,
        "to": [to_email],
        "subject": subject,
        "html": body,
    }
    if cc:
        payload["cc"] = [addr.strip() for addr in cc.split(",")]
    if bcc:
        payload["bcc"] = [addr.strip() for addr in bcc.split(",")]
    if attachments:
        payload["attachments"] = [
            {
                "filename": att["filename"],
                "content": base64.b64encode(att["content"]).decode("ascii"),
                "content_type": att["content_type"],
            }
            for att in attachments
        ]
    resend.Emails.send(payload)


def render_template(
    template: str, variables: dict[str, str], is_html: bool = True
) -> str:
    """Render a template by replacing {{var}} placeholders with substituted values.

    Substitution is single-pass so attacker-controlled values cannot re-expand
    as placeholders. When ``is_html`` is True (the default, used for email
    bodies) values are HTML-escaped so variables cannot inject tags, attributes,
    or event handlers. Pass ``is_html=False`` for plain-text contexts like the
    email subject line where escaping would produce ``&amp;`` artifacts.
    """
    def replacer(match):
        key = match.group(1)
        if key not in variables:
            return match.group(0)
        value = str(variables[key])
        return html.escape(value, quote=True) if is_html else value

    return re.sub(r"\{\{(\w+)\}\}", replacer, template)


class EmailService:
    """Service for email queue operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _validate_from_email(from_email: str | None) -> str | None:
        """Validate from_email against the configured EMAIL_FROM domain.

        Returns the from_email if valid, or None to fall back to default.
        """
        if not from_email:
            return None
        # Extract domain from the default EMAIL_FROM setting
        default_domain = settings.EMAIL_FROM.rsplit("@", 1)[-1] if "@" in settings.EMAIL_FROM else ""
        if not default_domain:
            return None
        email_domain = from_email.rsplit("@", 1)[-1] if "@" in from_email else ""
        if email_domain.lower() != default_domain.lower():
            logger.warning("Invalid from_email domain %s, using default", from_email)
            return None
        return from_email

    async def queue_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        sent_by_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        template_id: int | None = None,
        campaign_id: int | None = None,
        from_email: str | None = None,
        cc: str | None = None,
        bcc: str | None = None,
        reply_to_email_id: int | None = None,
        reply_to_inbound_id: int | None = None,
        attachments: list[EmailAttachment] | None = None,
    ) -> EmailQueue:
        """Create an email queue entry and attempt to send.

        ``attachments`` carries raw bytes through to the provider in
        memory only — the EmailQueue row has no column for them, so
        nothing is persisted server-side. Surfacing attachment metadata
        on the email log would require an Alembic migration; left out
        of this PR deliberately, with sender's "Sent" folder as the
        ground truth in the meantime.
        """
        from_email = self._validate_from_email(from_email)
        email = EmailQueue(
            to_email=to_email,
            from_email=from_email,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            sent_by_id=sent_by_id,
            entity_type=entity_type,
            entity_id=entity_id,
            template_id=template_id,
            campaign_id=campaign_id,
            status="pending",
            attempts=0,
        )
        self.db.add(email)
        await self.db.flush()

        from src.email.throttle import EmailThrottleService
        throttle = EmailThrottleService(self.db)
        if not await throttle.can_send():
            email.status = "throttled"
            tomorrow_9am = (datetime.now(UTC) + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            email.next_retry_at = tomorrow_9am
            await self.db.flush()
            return email

        await self._attempt_send(
            email,
            reply_to_email_id=reply_to_email_id,
            reply_to_inbound_id=reply_to_inbound_id,
            attachments=attachments,
        )
        return email

    async def _attempt_send(
        self,
        email: EmailQueue,
        *,
        reply_to_email_id: int | None = None,
        reply_to_inbound_id: int | None = None,
        attachments: list[EmailAttachment] | None = None,
    ) -> None:
        """Attempt to send via Gmail if connected, fall back to Resend.

        Attachments are passed through to the provider in-memory only;
        they are *not* persisted on the EmailQueue row, so if this send
        hits the retry path, the retry will go out without the
        attachment. That's acceptable for the current use case (quote /
        proposal PDFs are re-derivable from the entity) but worth noting
        before reusing this for attachments that can't be regenerated.
        """
        email.attempts += 1
        try:
            sent_via_gmail = False
            try:
                sent_via_gmail = await _try_gmail_send(
                    email,
                    self.db,
                    reply_to_email_id=reply_to_email_id,
                    reply_to_inbound_id=reply_to_inbound_id,
                    attachments=attachments,
                )
            except Exception as gmail_exc:
                logger.info("Gmail send failed for email %s, falling back to Resend: %s", email.id, gmail_exc)

            if not sent_via_gmail:
                if reply_to_email_id is not None or reply_to_inbound_id is not None:
                    logger.warning(
                        "Email %s is a reply but Gmail send skipped/failed — Resend fallback will not preserve thread headers",
                        email.id,
                    )
                await asyncio.to_thread(
                    send_email, email.to_email, email.subject, email.body,
                    email.from_email, email.cc, email.bcc,
                    attachments,
                )
                email.sent_via = "resend"

            email.status = "sent"
            email.sent_at = datetime.now(UTC)
            await _create_email_activity(self.db, email)
        except Exception as exc:
            email.error = str(exc)[:500]
            email.retry_count += 1
            if email.retry_count >= MAX_RETRIES:
                email.status = "failed"
                logger.warning("Email %s permanently failed after %d retries", email.id, email.retry_count)
            else:
                email.status = "retry"
                backoff_minutes = 2 ** email.retry_count
                email.next_retry_at = datetime.now(UTC) + timedelta(minutes=backoff_minutes)
        await self.db.flush()

    async def get_by_id(self, email_id: int) -> EmailQueue | None:
        result = await self.db.execute(
            select(EmailQueue).where(EmailQueue.id == email_id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        entity_type: str | None = None,
        entity_id: int | None = None,
        status: str | None = None,
        sent_by_id: int | None = None,
    ) -> tuple[list[EmailQueue], int]:
        """Get paginated list of emails with optional filters."""
        filters = []
        if entity_type:
            filters.append(EmailQueue.entity_type == entity_type)
        if entity_id is not None:
            filters.append(EmailQueue.entity_id == entity_id)
        if status:
            filters.append(EmailQueue.status == status)
        if sent_by_id is not None:
            filters.append(EmailQueue.sent_by_id == sent_by_id)

        count_query = select(func.count()).select_from(EmailQueue)
        query = select(EmailQueue).order_by(EmailQueue.created_at.desc())
        if filters:
            count_query = count_query.where(*filters)
            query = query.where(*filters)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def _record_tracking_event(
        self, email_id: int, count_attr: str, timestamp_attr: str,
    ) -> EmailQueue | None:
        """Increment a tracking counter and set the first-occurrence timestamp."""
        email = await self.get_by_id(email_id)
        if not email:
            return None
        setattr(email, count_attr, getattr(email, count_attr) + 1)
        if not getattr(email, timestamp_attr):
            setattr(email, timestamp_attr, datetime.now(UTC))
        await self.db.flush()
        return email

    async def record_open(self, email_id: int) -> EmailQueue | None:
        """Record an email open event."""
        return await self._record_tracking_event(email_id, "open_count", "opened_at")

    async def record_click(self, email_id: int) -> EmailQueue | None:
        """Record an email click event."""
        return await self._record_tracking_event(email_id, "click_count", "clicked_at")

    async def process_retries(self) -> int:
        """Retry emails that are due for retry. Returns the count of retried emails."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(EmailQueue).where(
                and_(
                    EmailQueue.status == "retry",
                    EmailQueue.next_retry_at <= now,
                )
            )
        )
        due_emails = list(result.scalars().all())
        for email in due_emails:
            await self._attempt_send(email)
        return len(due_emails)

    async def send_template_email(
        self,
        to_email: str,
        template_id: int,
        variables: dict[str, str] | None = None,
        sent_by_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        use_branded_wrapper: bool = False,
        branding: dict | None = None,
    ) -> EmailQueue:
        """Send an email using a template.

        When use_branded_wrapper is True and branding is provided, the
        rendered body is wrapped in the tenant's branded email template.
        """
        from src.campaigns.models import EmailTemplate
        result = await self.db.execute(
            select(EmailTemplate).where(EmailTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise ValueError(f"Template {template_id} not found")

        vars_dict = variables or {}
        subject = render_template(template.subject_template, vars_dict, is_html=False)
        body = render_template(template.body_template or "", vars_dict)

        if use_branded_wrapper and branding:
            body = render_branded_email(
                branding=branding,
                subject=subject,
                headline="",
                body_html=body,
            )

        return await self.queue_email(
            to_email=to_email,
            subject=subject,
            body=body,
            sent_by_id=sent_by_id,
            entity_type=entity_type,
            entity_id=entity_id,
            template_id=template_id,
        )

    async def send_campaign_emails(
        self,
        campaign_id: int,
        template_id: int,
        variables: dict[str, str] | None = None,
        sent_by_id: int | None = None,
    ) -> list[EmailQueue]:
        """Send branded emails to all members of a campaign.

        Wraps each email in the tenant's branded template with an
        unsubscribe link in the footer.
        """
        from src.campaigns.models import CampaignMember, EmailTemplate
        from src.email.branded_templates import render_campaign_wrapper

        branding = TenantBrandingHelper.get_default_branding()
        if sent_by_id:
            branding = await TenantBrandingHelper.get_branding_for_user(
                self.db, sent_by_id
            )

        tmpl_result = await self.db.execute(
            select(EmailTemplate).where(EmailTemplate.id == template_id)
        )
        template = tmpl_result.scalar_one_or_none()
        if not template:
            raise ValueError(f"Template {template_id} not found")

        vars_dict = variables or {}
        subject = render_template(template.subject_template, vars_dict, is_html=False)
        raw_body = render_template(template.body_template or "", vars_dict)

        result = await self.db.execute(
            select(CampaignMember).where(CampaignMember.campaign_id == campaign_id)
        )
        members = result.scalars().all()

        sent_emails = []
        for member in members:
            email_addr = await self.get_member_email(member)
            if email_addr:
                unsubscribe_url = (
                    f"/api/campaigns/{campaign_id}/unsubscribe"
                    f"?member_id={member.id}&email={email_addr}"
                )
                branded_body = render_campaign_wrapper(
                    branding=branding,
                    campaign_body=raw_body,
                    unsubscribe_url=unsubscribe_url,
                )
                email = await self.queue_email(
                    to_email=email_addr,
                    subject=subject,
                    body=branded_body,
                    sent_by_id=sent_by_id,
                    entity_type=member.member_type,
                    entity_id=member.member_id,
                    template_id=template_id,
                    campaign_id=campaign_id,
                )
                sent_emails.append(email)

        return sent_emails

    async def get_member_email(self, member) -> str | None:
        """Get the email address for a campaign member."""
        if member.member_type in ("contact", "contacts"):
            from src.contacts.models import Contact
            result = await self.db.execute(
                select(Contact.email).where(Contact.id == member.member_id)
            )
        elif member.member_type in ("lead", "leads"):
            from src.leads.models import Lead
            result = await self.db.execute(
                select(Lead.email).where(Lead.id == member.member_id)
            )
        else:
            return None
        return result.scalar_one_or_none()

    async def send_branded_email(
        self,
        to_email: str,
        subject: str,
        headline: str,
        body_html: str,
        sent_by_id: int,
        cta_text: str | None = None,
        cta_url: str | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
    ) -> EmailQueue:
        """Send an email wrapped in the tenant-branded template.

        1. Fetches tenant branding for the sending user.
        2. Wraps content in the branded HTML template.
        3. Uses email_from_name / email_from_address from TenantSettings.
        4. Queues and sends via existing SMTP infrastructure.
        """
        branding = await TenantBrandingHelper.get_branding_for_user(
            self.db, sent_by_id
        )

        html = render_branded_email(
            branding=branding,
            subject=subject,
            headline=headline,
            body_html=body_html,
            cta_text=cta_text,
            cta_url=cta_url,
        )

        return await self.queue_email(
            to_email=to_email,
            subject=subject,
            body=html,
            sent_by_id=sent_by_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    async def store_inbound_email(
        self,
        resend_email_id: str,
        from_email: str,
        to_email: str,
        subject: str,
        received_at: datetime,
        cc: str | None = None,
        bcc: str | None = None,
        body_text: str | None = None,
        body_html: str | None = None,
        message_id: str | None = None,
        in_reply_to: str | None = None,
        attachments: list | None = None,
    ) -> InboundEmail:
        """Store an inbound email and auto-match to a contact."""
        from src.contacts.models import Contact

        inbound = InboundEmail(
            resend_email_id=resend_email_id,
            from_email=from_email,
            to_email=to_email,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            message_id=message_id,
            in_reply_to=in_reply_to,
            attachments=attachments,
            received_at=received_at,
        )

        # Skip empty from_email: matching "" would attach inbound mail to any
        # contact whose email column happens to be blank. Use alias-aware
        # lookup so alternate addresses also link to the right contact.
        if from_email:
            from src.contacts.alias_match import find_contact_id_by_any_email
            entity_type, entity_id = await find_contact_id_by_any_email([from_email], self.db)
            if entity_id is not None:
                inbound.entity_type = entity_type
                inbound.entity_id = entity_id

        self.db.add(inbound)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            # Duplicate resend_email_id — return existing record (idempotent)
            result = await self.db.execute(
                select(InboundEmail).where(
                    InboundEmail.resend_email_id == resend_email_id
                )
            )
            return result.scalar_one()

        # Log as activity on matched contact
        if inbound.entity_type == "contacts" and inbound.entity_id is not None:
            from src.activities.models import Activity
            from src.contacts.models import Contact
            contact_result = await self.db.execute(
                select(Contact).where(Contact.id == inbound.entity_id)
            )
            matched_contact = contact_result.scalar_one_or_none()
            if matched_contact is not None:
                activity = Activity(
                    activity_type="email",
                    subject=f"Inbound email: {subject}",
                    description=body_text[:500] if body_text else None,
                    entity_type="contacts",
                    entity_id=matched_contact.id,
                    email_to=to_email,
                    is_completed=True,
                    owner_id=matched_contact.owner_id,
                )
                self.db.add(activity)
                await self.db.flush()

        return inbound

    async def search_emails(
        self,
        q: str,
        user_id: int,
        page: int = 1,
        page_size: int = 25,
        entity_type: str | None = None,
        entity_id: int | None = None,
    ) -> tuple[list[dict], int]:
        """Search emails by keyword across subject, body, from, to, cc, bcc.

        Scoped to the requesting user: email_queue rows by sent_by_id, inbound_email
        rows by the to_email matching the user's connected Gmail address.
        """
        from src.integrations.gmail.models import GmailConnection

        gmail_result = await self.db.execute(
            select(GmailConnection.email).where(
                GmailConnection.user_id == user_id,
                GmailConnection.revoked_at.is_(None),
            )
        )
        user_gmail = gmail_result.scalar_one_or_none()

        # Escape LIKE metacharacters so a user typing `%` matches literally
        # instead of "every row I have access to". Keep `\` first so we
        # don't double-escape our own escapes.
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pat = f"%{escaped}%"
        sent_filters = [
            EmailQueue.sent_by_id == user_id,
            or_(
                EmailQueue.subject.ilike(pat, escape="\\"),
                EmailQueue.body.ilike(pat, escape="\\"),
                EmailQueue.from_email.ilike(pat, escape="\\"),
                EmailQueue.to_email.ilike(pat, escape="\\"),
                EmailQueue.cc.ilike(pat, escape="\\"),
                EmailQueue.bcc.ilike(pat, escape="\\"),
            ),
        ]
        if entity_type:
            sent_filters.append(EmailQueue.entity_type == entity_type)
        if entity_id is not None:
            sent_filters.append(EmailQueue.entity_id == entity_id)

        outbound_q = (
            select(
                EmailQueue.id.label("id"),
                literal("sent").label("kind"),
                EmailQueue.subject.label("subject"),
                EmailQueue.body.label("body"),
                func.coalesce(EmailQueue.from_email, literal(settings.EMAIL_FROM)).label("from_email"),
                EmailQueue.to_email.label("to_email"),
                func.coalesce(EmailQueue.sent_at, EmailQueue.created_at).label("sent_at"),
                EmailQueue.thread_id.label("thread_id"),
                EmailQueue.entity_type.label("entity_type"),
                EmailQueue.entity_id.label("entity_id"),
            )
            .where(*sent_filters)
        )

        recv_filters = [
            or_(
                InboundEmail.subject.ilike(pat, escape="\\"),
                InboundEmail.body_text.ilike(pat, escape="\\"),
                InboundEmail.body_html.ilike(pat, escape="\\"),
                InboundEmail.from_email.ilike(pat, escape="\\"),
                InboundEmail.to_email.ilike(pat, escape="\\"),
                InboundEmail.cc.ilike(pat, escape="\\"),
                InboundEmail.bcc.ilike(pat, escape="\\"),
            ),
        ]
        if user_gmail:
            recv_filters.append(
                func.lower(InboundEmail.to_email) == user_gmail.lower()
            )
        else:
            # No Gmail connection — no inbound results can be scoped to this user
            recv_filters.append(literal(False))
        if entity_type:
            recv_filters.append(InboundEmail.entity_type == entity_type)
        if entity_id is not None:
            recv_filters.append(InboundEmail.entity_id == entity_id)

        inbound_q = (
            select(
                InboundEmail.id.label("id"),
                literal("received").label("kind"),
                InboundEmail.subject.label("subject"),
                InboundEmail.body_text.label("body"),
                InboundEmail.from_email.label("from_email"),
                InboundEmail.to_email.label("to_email"),
                InboundEmail.received_at.label("sent_at"),
                InboundEmail.thread_id.label("thread_id"),
                InboundEmail.entity_type.label("entity_type"),
                InboundEmail.entity_id.label("entity_id"),
            )
            .where(*recv_filters)
        )

        combined = union_all(outbound_q, inbound_q).subquery()
        count_q = select(func.count()).select_from(combined)
        total = (await self.db.execute(count_q)).scalar() or 0

        offset = (page - 1) * page_size
        data_q = (
            select(combined)
            # Tiebreakers on (kind, id) prevent UNION ALL pagination from
            # shuffling rows that share a sent_at timestamp (common for
            # batch-queued emails) — without these, page 1 and page 2 can
            # return overlapping or skipped rows.
            .order_by(combined.c.sent_at.desc(), combined.c.kind.desc(), combined.c.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(data_q)).mappings().all()

        def _snippet(body: str | None, pattern: str) -> str:
            if not body:
                return ""
            low = body.lower()
            pos = low.find(pattern.lower())
            if pos >= 0:
                start = max(0, pos - 60)
                return body[start : start + 200]
            return body[:200]

        items = [
            {
                "id": row["id"],
                "kind": row["kind"],
                "subject": row["subject"],
                "snippet": _snippet(row["body"], q),
                "from_email": row["from_email"],
                "to_email": row["to_email"],
                "sent_at": row["sent_at"],
                "thread_id": row["thread_id"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
            }
            for row in rows
        ]
        return items, total

    async def get_thread(
        self,
        entity_type: str,
        entity_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        """Get unified email thread (inbound + outbound) for an entity.

        Uses SQL UNION ALL with ORDER BY + LIMIT/OFFSET at the database level.
        """
        outbound_q = (
            select(
                EmailQueue.id.label("id"),
                literal("outbound").label("direction"),
                func.coalesce(EmailQueue.from_email, literal(settings.EMAIL_FROM)).label("from_email"),
                EmailQueue.to_email.label("to_email"),
                EmailQueue.cc.label("cc"),
                EmailQueue.subject.label("subject"),
                EmailQueue.body.label("body"),
                literal(None).label("body_html"),
                func.coalesce(EmailQueue.sent_at, EmailQueue.created_at).label("timestamp"),
                EmailQueue.status.label("status"),
                EmailQueue.open_count.label("open_count"),
                literal(None).label("attachments"),
                EmailQueue.thread_id.label("thread_id"),
            )
            .where(
                EmailQueue.entity_type == entity_type,
                EmailQueue.entity_id == entity_id,
            )
        )

        inbound_q = (
            select(
                InboundEmail.id.label("id"),
                literal("inbound").label("direction"),
                InboundEmail.from_email.label("from_email"),
                InboundEmail.to_email.label("to_email"),
                InboundEmail.cc.label("cc"),
                InboundEmail.subject.label("subject"),
                InboundEmail.body_text.label("body"),
                InboundEmail.body_html.label("body_html"),
                InboundEmail.received_at.label("timestamp"),
                literal(None).label("status"),
                literal(None).label("open_count"),
                literal(None).label("attachments"),
                InboundEmail.thread_id.label("thread_id"),
            )
            .where(
                InboundEmail.entity_type == entity_type,
                InboundEmail.entity_id == entity_id,
            )
        )

        combined = union_all(outbound_q, inbound_q).subquery()

        count_q = select(func.count()).select_from(combined)
        total = (await self.db.execute(count_q)).scalar() or 0

        offset = (page - 1) * page_size
        data_q = (
            select(combined)
            .order_by(combined.c.timestamp.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(data_q)
        rows = result.mappings().all()

        items = [dict(row) for row in rows]
        return items, total

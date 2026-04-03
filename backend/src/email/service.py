"""Email service layer - handles sending, tracking, and queue management."""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple, Dict

import resend
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.email.models import EmailQueue, InboundEmail
from src.email.branded_templates import TenantBrandingHelper, render_branded_email
from src.core.constants import DEFAULT_PAGE_SIZE

logger = logging.getLogger(__name__)

MAX_RETRIES = 5


def send_email(
    to_email: str,
    subject: str,
    body: str,
    from_email: Optional[str] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
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
    resend.Emails.send(payload)


def render_template(template: str, variables: Dict[str, str]) -> str:
    """Render a template string by replacing {{var}} placeholders."""
    def replacer(match):
        key = match.group(1)
        return variables.get(key, match.group(0))

    return re.sub(r"\{\{(\w+)\}\}", replacer, template)


class EmailService:
    """Service for email queue operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def queue_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        sent_by_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        template_id: Optional[int] = None,
        campaign_id: Optional[int] = None,
        from_email: Optional[str] = None,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
    ) -> EmailQueue:
        """Create an email queue entry and attempt to send."""
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

        # Check daily send limit before sending
        from src.email.throttle import EmailThrottleService
        throttle = EmailThrottleService(self.db)
        if not await throttle.can_send():
            email.status = "throttled"
            # Schedule for next day at 9 AM UTC
            tomorrow_9am = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            email.next_retry_at = tomorrow_9am
            await self.db.flush()
            return email

        # Attempt immediate send
        await self._attempt_send(email)
        return email

    async def _attempt_send(self, email: EmailQueue) -> None:
        """Attempt to send an email, updating status accordingly.

        On failure, sets status to 'retry' with exponential backoff
        (2^retry_count minutes) up to MAX_RETRIES, then marks as 'failed'.
        """
        email.attempts += 1
        try:
            await asyncio.to_thread(
                send_email, email.to_email, email.subject, email.body,
                email.from_email, email.cc, email.bcc,
            )
            email.status = "sent"
            email.sent_at = datetime.now(timezone.utc)
        except Exception as exc:
            email.error = str(exc)[:500]
            email.retry_count += 1
            if email.retry_count >= MAX_RETRIES:
                email.status = "failed"
                logger.warning("Email %s permanently failed after %d retries", email.id, email.retry_count)
            else:
                email.status = "retry"
                backoff_minutes = 2 ** email.retry_count
                email.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)
        await self.db.flush()

    async def get_by_id(self, email_id: int) -> Optional[EmailQueue]:
        """Get an email by ID."""
        result = await self.db.execute(
            select(EmailQueue).where(EmailQueue.id == email_id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        status: Optional[str] = None,
        sent_by_id: Optional[int] = None,
    ) -> Tuple[List[EmailQueue], int]:
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

        # Count + Fetch
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
    ) -> Optional[EmailQueue]:
        """Increment a tracking counter and set the first-occurrence timestamp."""
        email = await self.get_by_id(email_id)
        if not email:
            return None
        setattr(email, count_attr, getattr(email, count_attr) + 1)
        if not getattr(email, timestamp_attr):
            setattr(email, timestamp_attr, datetime.now(timezone.utc))
        await self.db.flush()
        return email

    async def record_open(self, email_id: int) -> Optional[EmailQueue]:
        """Record an email open event."""
        return await self._record_tracking_event(email_id, "open_count", "opened_at")

    async def record_click(self, email_id: int) -> Optional[EmailQueue]:
        """Record an email click event."""
        return await self._record_tracking_event(email_id, "click_count", "clicked_at")

    async def process_retries(self) -> int:
        """Retry emails that are due for retry. Returns the count of retried emails."""
        now = datetime.now(timezone.utc)
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
        variables: Optional[Dict[str, str]] = None,
        sent_by_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        use_branded_wrapper: bool = False,
        branding: Optional[dict] = None,
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
        subject = render_template(template.subject_template, vars_dict)
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
        variables: Optional[Dict[str, str]] = None,
        sent_by_id: Optional[int] = None,
    ) -> List[EmailQueue]:
        """Send branded emails to all members of a campaign.

        Wraps each email in the tenant's branded template with an
        unsubscribe link in the footer.
        """
        from src.campaigns.models import CampaignMember, EmailTemplate
        from src.email.branded_templates import render_campaign_wrapper

        # Fetch tenant branding for the sending user
        branding = TenantBrandingHelper.get_default_branding()
        if sent_by_id:
            branding = await TenantBrandingHelper.get_branding_for_user(
                self.db, sent_by_id
            )

        # Resolve template body once
        tmpl_result = await self.db.execute(
            select(EmailTemplate).where(EmailTemplate.id == template_id)
        )
        template = tmpl_result.scalar_one_or_none()
        if not template:
            raise ValueError(f"Template {template_id} not found")

        vars_dict = variables or {}
        subject = render_template(template.subject_template, vars_dict)
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

    async def get_member_email(self, member) -> Optional[str]:
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
        cta_text: Optional[str] = None,
        cta_url: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
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
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
        message_id: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        attachments: Optional[list] = None,
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

        # Auto-match to contact by from_email
        result = await self.db.execute(
            select(Contact).where(Contact.email == from_email)
        )
        contact = result.scalar_one_or_none()
        if contact:
            inbound.entity_type = "contacts"
            inbound.entity_id = contact.id

        self.db.add(inbound)
        await self.db.flush()

        # Log as activity on matched contact
        if contact:
            from src.activities.models import Activity
            activity = Activity(
                activity_type="email",
                subject=f"Inbound email: {subject}",
                description=body_text[:500] if body_text else None,
                entity_type="contacts",
                entity_id=contact.id,
                email_to=to_email,
                is_completed=True,
                owner_id=contact.owner_id,
            )
            self.db.add(activity)
            await self.db.flush()

        return inbound

    async def get_thread(
        self,
        entity_type: str,
        entity_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[Dict], int]:
        """Get unified email thread (inbound + outbound) for an entity."""
        # Count outbound
        outbound_count_q = select(func.count()).select_from(
            select(EmailQueue.id).where(
                EmailQueue.entity_type == entity_type,
                EmailQueue.entity_id == entity_id,
            ).subquery()
        )
        # Count inbound
        inbound_count_q = select(func.count()).select_from(
            select(InboundEmail.id).where(
                InboundEmail.entity_type == entity_type,
                InboundEmail.entity_id == entity_id,
            ).subquery()
        )

        outbound_total = (await self.db.execute(outbound_count_q)).scalar() or 0
        inbound_total = (await self.db.execute(inbound_count_q)).scalar() or 0
        total = outbound_total + inbound_total

        # Fetch outbound emails
        outbound_result = await self.db.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == entity_type,
                EmailQueue.entity_id == entity_id,
            )
        )
        outbound_emails = list(outbound_result.scalars().all())

        # Fetch inbound emails
        inbound_result = await self.db.execute(
            select(InboundEmail).where(
                InboundEmail.entity_type == entity_type,
                InboundEmail.entity_id == entity_id,
            )
        )
        inbound_emails = list(inbound_result.scalars().all())

        # Merge into unified list
        items = []
        for e in outbound_emails:
            items.append({
                "id": e.id,
                "direction": "outbound",
                "from_email": e.from_email or settings.EMAIL_FROM,
                "to_email": e.to_email,
                "cc": e.cc,
                "subject": e.subject,
                "body": e.body,
                "body_html": None,
                "timestamp": e.sent_at or e.created_at,
                "status": e.status,
                "open_count": e.open_count,
                "attachments": None,
            })
        for e in inbound_emails:
            items.append({
                "id": e.id,
                "direction": "inbound",
                "from_email": e.from_email,
                "to_email": e.to_email,
                "cc": e.cc,
                "subject": e.subject,
                "body": e.body_text,
                "body_html": e.body_html,
                "timestamp": e.received_at,
                "status": None,
                "open_count": None,
                "attachments": e.attachments,
            })

        # Sort by timestamp descending (newest first)
        # Normalize naive datetimes to UTC for comparison (SQLite returns naive)
        def _sort_key(item):
            ts = item["timestamp"]
            if ts and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts

        items.sort(key=_sort_key, reverse=True)

        # Paginate
        offset = (page - 1) * page_size
        paginated = items[offset:offset + page_size]

        return paginated, total

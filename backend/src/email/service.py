"""Email service layer - handles sending, tracking, and queue management."""

import os
import re
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List, Tuple, Dict

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.email.models import EmailQueue
from src.email.branded_templates import TenantBrandingHelper, render_branded_email
from src.core.constants import DEFAULT_PAGE_SIZE


def get_smtp_config() -> dict:
    """Read SMTP configuration from environment variables."""
    return {
        "host": os.getenv("SMTP_HOST", "localhost"),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from_email": os.getenv("SMTP_FROM", "noreply@crm.local"),
        "use_tls": os.getenv("SMTP_USE_TLS", "true").lower() == "true",
    }


def send_email_smtp(to_email: str, subject: str, body: str) -> None:
    """Send an email via SMTP. Raises on failure."""
    config = get_smtp_config()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["from_email"]
    msg["To"] = to_email
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP(config["host"], config["port"]) as server:
        if config["use_tls"]:
            server.starttls()
        if config["user"] and config["password"]:
            server.login(config["user"], config["password"])
        server.sendmail(config["from_email"], [to_email], msg.as_string())


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
    ) -> EmailQueue:
        """Create an email queue entry and attempt to send."""
        email = EmailQueue(
            to_email=to_email,
            subject=subject,
            body=body,
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

        # Attempt immediate send
        await self._attempt_send(email)
        return email

    async def _attempt_send(self, email: EmailQueue) -> None:
        """Attempt to send an email, updating status accordingly."""
        email.attempts += 1
        try:
            send_email_smtp(email.to_email, email.subject, email.body)
            email.status = "sent"
            email.sent_at = datetime.now(timezone.utc)
        except Exception as exc:
            email.status = "failed"
            email.error = str(exc)[:500]
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

        # Count
        if filters:
            count_query = select(func.count()).select_from(
                select(EmailQueue.id).where(*filters).subquery()
            )
        else:
            count_query = select(func.count()).select_from(EmailQueue)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch
        query = select(EmailQueue).order_by(EmailQueue.created_at.desc())
        if filters:
            query = query.where(*filters)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def record_open(self, email_id: int) -> Optional[EmailQueue]:
        """Record an email open event."""
        email = await self.get_by_id(email_id)
        if not email:
            return None
        email.open_count += 1
        if not email.opened_at:
            email.opened_at = datetime.now(timezone.utc)
        await self.db.flush()
        return email

    async def record_click(self, email_id: int) -> Optional[EmailQueue]:
        """Record an email click event."""
        email = await self.get_by_id(email_id)
        if not email:
            return None
        email.click_count += 1
        if not email.clicked_at:
            email.clicked_at = datetime.now(timezone.utc)
        await self.db.flush()
        return email

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
            email_addr = await self._get_member_email(member)
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

    async def _get_member_email(self, member) -> Optional[str]:
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

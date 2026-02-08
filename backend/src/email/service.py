"""Email service for sending and tracking emails."""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Optional, Tuple, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.email.models import EmailQueue


def get_smtp_config() -> dict:
    """Get SMTP configuration from environment variables."""
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
        server.sendmail(config["from_email"], to_email, msg.as_string())


def render_template(template_str: str, variables: dict) -> str:
    """Render a template string with {{variable}} placeholders."""
    result = template_str
    for key, value in variables.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


class EmailService:
    """Service for email queue management and sending."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def queue_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        sent_by_id: int,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        template_id: Optional[int] = None,
        campaign_id: Optional[int] = None,
    ) -> EmailQueue:
        """Queue an email and attempt to send it immediately."""
        email = EmailQueue(
            to_email=to_email,
            subject=subject,
            body=body,
            status="pending",
            entity_type=entity_type,
            entity_id=entity_id,
            template_id=template_id,
            campaign_id=campaign_id,
            sent_by_id=sent_by_id,
        )
        self.db.add(email)
        await self.db.flush()

        await self._attempt_send(email)
        return email

    async def _attempt_send(self, email: EmailQueue) -> None:
        """Attempt to send an email, updating status accordingly."""
        email.attempts += 1
        try:
            send_email_smtp(email.to_email, email.subject, email.body)
            email.status = "sent"
            email.sent_at = datetime.now(timezone.utc)
        except Exception as e:
            email.status = "failed"
            email.error = str(e)

    async def get_by_id(self, email_id: int) -> Optional[EmailQueue]:
        """Get an email by ID."""
        result = await self.db.execute(
            select(EmailQueue).where(EmailQueue.id == email_id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = 20,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> Tuple[List[EmailQueue], int]:
        """Get paginated list of emails with optional filters."""
        query = select(EmailQueue)
        count_query = select(func.count()).select_from(EmailQueue)

        if entity_type:
            query = query.where(EmailQueue.entity_type == entity_type)
            count_query = count_query.where(EmailQueue.entity_type == entity_type)
        if entity_id is not None:
            query = query.where(EmailQueue.entity_id == entity_id)
            count_query = count_query.where(EmailQueue.entity_id == entity_id)
        if status:
            query = query.where(EmailQueue.status == status)
            count_query = count_query.where(EmailQueue.status == status)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.order_by(EmailQueue.created_at.desc()).offset(offset).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def record_open(self, email_id: int) -> Optional[EmailQueue]:
        """Record an email open event."""
        email = await self.get_by_id(email_id)
        if email:
            email.open_count += 1
            if not email.opened_at:
                email.opened_at = datetime.now(timezone.utc)
        return email

    async def record_click(self, email_id: int) -> Optional[EmailQueue]:
        """Record an email click event."""
        email = await self.get_by_id(email_id)
        if email:
            email.click_count += 1
            if not email.clicked_at:
                email.clicked_at = datetime.now(timezone.utc)
        return email

    async def send_template_email(
        self,
        to_email: str,
        template_id: int,
        variables: dict,
        sent_by_id: int,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
    ) -> EmailQueue:
        """Send an email using a template."""
        from src.campaigns.models import EmailTemplate

        result = await self.db.execute(
            select(EmailTemplate).where(EmailTemplate.id == template_id)
        )
        template = result.scalar_one_or_none()
        if not template:
            raise ValueError(f"Email template {template_id} not found")

        subject = render_template(template.subject_template, variables)
        body = render_template(template.body_template, variables)

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
        self, campaign_id: int, sent_by_id: int
    ) -> List[EmailQueue]:
        """Send emails to all pending members of a campaign."""
        from src.campaigns.models import CampaignMember

        result = await self.db.execute(
            select(CampaignMember).where(
                CampaignMember.campaign_id == campaign_id,
                CampaignMember.status == "pending",
            )
        )
        members = list(result.scalars().all())

        sent_emails = []
        for member in members:
            email_addr = await self._get_member_email(member)
            if email_addr:
                email = await self.queue_email(
                    to_email=email_addr,
                    subject=f"Campaign #{campaign_id}",
                    body=f"Campaign message for member {member.member_id}",
                    sent_by_id=sent_by_id,
                    campaign_id=campaign_id,
                )
                sent_emails.append(email)

        return sent_emails

    async def _get_member_email(self, member) -> Optional[str]:
        """Resolve email address from a campaign member."""
        if member.member_type == "contact":
            from src.contacts.models import Contact
            result = await self.db.execute(
                select(Contact.email).where(Contact.id == member.member_id)
            )
        elif member.member_type == "lead":
            from src.leads.models import Lead
            result = await self.db.execute(
                select(Lead.email).where(Lead.id == member.member_id)
            )
        else:
            return None
        return result.scalar_one_or_none()

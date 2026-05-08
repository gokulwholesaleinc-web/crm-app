"""Notification service layer."""

import logging
import os

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.account.notification_gate import should_notify_in_app, should_send_email
from src.auth.models import User
from src.core.constants import DEFAULT_PAGE_SIZE
from src.notifications.models import Notification

logger = logging.getLogger(__name__)


# Default front-end origin used when ``FRONTEND_URL`` isn't set (local
# dev). All deep links in branded notification emails route through
# this. Pulled out so workers don't drift on the env-var name.
def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:3000")


def _deep_link(entity_type: str, entity_id: int, *, suffix: str = "") -> str:
    """Build a CRM-frontend deep link for the given entity row.

    Accepts either a bare entity slug (``leads``) or a leading-slash
    path (``/contacts``) — necessary because the existing dispatchers
    are called with both shapes from different parts of the codebase.
    ``suffix`` is appended verbatim (e.g. ``?tab=email``) for callers
    that need a query string or hash fragment.
    """
    segment = entity_type if entity_type.startswith("/") else f"/{entity_type}"
    return f"{_frontend_url()}{segment}/{entity_id}{suffix}"


async def _user_email(db: AsyncSession, user_id: int) -> str | None:
    """Look up an authenticated user's primary email.

    Returns ``None`` when the user is missing or has no email — the
    caller treats that as "skip the email send" without raising, since
    the in-app notification has already been written.
    """
    user = await db.get(User, user_id)
    if not user or not user.email:
        return None
    return user.email


async def _queue_notification_email(
    db: AsyncSession,
    *,
    user_id: int,
    event_type: str,
    subject: str,
    body_html: str,
    entity_type: str | None,
    entity_id: int | None,
) -> None:
    """Best-effort email send for a matrix-gated notification event.

    Caller is expected to have already checked
    :func:`should_send_email`; this helper resolves the user's email,
    enqueues the message via :class:`EmailService`, and swallows transport
    failures with a warning so the in-app notification stays delivered.
    ``sent_by_id`` is the recipient — outbound rows are visible to the
    recipient on their email log without leaking through participant
    overlap to anyone else.
    """
    to_email = await _user_email(db, user_id)
    if not to_email:
        logger.debug(
            "notif email skipped: user_id=%s has no email (event=%s)",
            user_id, event_type,
        )
        return
    try:
        from src.email.service import EmailService

        email_service = EmailService(db)
        await email_service.queue_email(
            to_email=to_email,
            subject=subject,
            body=body_html,
            sent_by_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    except Exception:
        # Bumped to ERROR (was WARNING): a failure here means the user
        # gets no email despite the matrix gate saying they should.
        # That covers both transport failures (Gmail outage) and
        # programming errors (TypeError on EmailQueue, AttributeError
        # from a future field rename). Either deserves a real alarm.
        logger.error(
            "notification_email_dispatch_failed user_id=%s event=%s",
            user_id, event_type,
            exc_info=True,
        )


class NotificationService:
    """Service for notification CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_notification(
        self,
        user_id: int,
        type: str,
        title: str,
        message: str,
        entity_type: str | None = None,
        entity_id: int | None = None,
    ) -> Notification:
        """Create a new notification."""
        notif = Notification(
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        self.db.add(notif)
        await self.db.flush()
        await self.db.refresh(notif)
        return notif

    async def get_by_id(self, notification_id: int) -> Notification | None:
        result = await self.db.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int]:
        """Get paginated notifications for a user."""
        filters = [Notification.user_id == user_id]
        if unread_only:
            filters.append(Notification.is_read == False)

        # Count
        count_query = select(func.count()).select_from(
            select(Notification.id).where(*filters).subquery()
        )
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Fetch
        query = (
            select(Notification)
            .where(*filters)
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def mark_read(self, notification_id: int, user_id: int) -> Notification | None:
        """Mark a notification as read."""
        notif = await self.get_by_id(notification_id)
        if not notif or notif.user_id != user_id:
            return None
        notif.is_read = True
        await self.db.flush()
        await self.db.refresh(notif)
        return notif

    async def mark_all_read(self, user_id: int) -> int:
        """Mark all notifications as read for a user. Returns count updated."""
        stmt = (
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)
            .values(is_read=True)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount

    async def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications for a user."""
        result = await self.db.execute(
            select(func.count()).where(
                Notification.user_id == user_id,
                Notification.is_read == False,
            )
        )
        return result.scalar() or 0

    async def delete_notification(self, notification_id: int, user_id: int) -> bool:
        """Delete a single notification. Returns True if deleted."""
        notif = await self.get_by_id(notification_id)
        if not notif or notif.user_id != user_id:
            return False
        await self.db.delete(notif)
        await self.db.flush()
        return True

    async def delete_all_notifications(self, user_id: int) -> int:
        """Delete all notifications for a user. Returns count deleted."""
        stmt = delete(Notification).where(Notification.user_id == user_id)
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount


async def notify_on_assignment(
    db: AsyncSession,
    user_id: int,
    entity_type: str,
    entity_id: int,
    entity_name: str,
    *,
    assigner_name: str | None = None,
    entity_email: str | None = None,
    entity_company: str | None = None,
) -> Notification | None:
    """Create a notification when an entity is assigned to a user.

    The optional ``assigner_name``/``entity_email``/``entity_company``
    keyword arguments populate the branded email; callers that haven't
    been migrated yet still get the in-app notification (and an email
    with whatever metadata is available, including just the entity
    name).
    """
    notif: Notification | None = None
    if await should_notify_in_app(db, user_id, "lead_assigned"):
        service = NotificationService(db)
        notif = await service.create_notification(
            user_id=user_id,
            type="assignment",
            title=f"{entity_type.rstrip('s').capitalize()} assigned to you",
            message=f"You have been assigned {entity_name}",
            entity_type=entity_type,
            entity_id=entity_id,
        )

    if await should_send_email(db, user_id, "lead_assigned"):
        from src.email.branded_templates import (
            TenantBrandingHelper,
            render_lead_assigned_email,
        )

        branding = await TenantBrandingHelper.get_branding_for_user(db, user_id)
        deep_link = _deep_link(entity_type, entity_id)
        subject, body = render_lead_assigned_email(
            branding,
            {
                "lead_full_name": entity_name,
                "lead_email": entity_email or "",
                "lead_company_name": entity_company or "",
                "lead_url": deep_link,
                "assigner_name": assigner_name or "",
            },
        )
        await _queue_notification_email(
            db,
            user_id=user_id,
            event_type="lead_assigned",
            subject=subject,
            body_html=body,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    return notif


async def notify_on_stage_change(
    db: AsyncSession,
    user_id: int,
    entity_type: str,
    entity_id: int,
    entity_name: str,
    old_stage: str,
    new_stage: str,
) -> Notification | None:
    """Create a notification when a pipeline stage changes.

    NOT gated on user prefs in v1 — the Settings UI matrix doesn't
    surface a `stage_change` toggle, and the parallel event-bus path
    (`opportunity.stage_changed` via the notification_event_handler)
    isn't in `_MATRIX_EVENT_NAMES` either, so gating only this path
    would create a confusing asymmetry. When the UI gains a stage-
    change toggle, gate both paths together.
    """
    service = NotificationService(db)
    return await service.create_notification(
        user_id=user_id,
        type="stage_change",
        title=f"Stage changed: {entity_name}",
        message=f"Moved from {old_stage} to {new_stage}",
        entity_type=entity_type,
        entity_id=entity_id,
    )


async def notify_on_mention(
    db: AsyncSession,
    mentioned_user_id: int,
    author_name: str,
    entity_type: str,
    entity_id: int,
    content_snippet: str,
    *,
    entity_label: str | None = None,
) -> Notification | None:
    """Create a notification when a user is @mentioned.

    ``entity_label`` is the human-readable name of the host entity
    (e.g. "Acme - Q3 Renewal" for an opportunity); when provided it
    flows into the email subject and body for context. Falls back to
    the entity_type slug when absent.
    """
    notif: Notification | None = None
    if await should_notify_in_app(db, mentioned_user_id, "mention"):
        service = NotificationService(db)
        notif = await service.create_notification(
            user_id=mentioned_user_id,
            type="mention",
            title=f"{author_name} mentioned you",
            message=content_snippet[:200],
            entity_type=entity_type,
            entity_id=entity_id,
        )

    if await should_send_email(db, mentioned_user_id, "mention"):
        from src.email.branded_templates import (
            TenantBrandingHelper,
            render_mention_email,
        )

        branding = await TenantBrandingHelper.get_branding_for_user(
            db, mentioned_user_id,
        )
        deep_link = _deep_link(entity_type, entity_id)
        subject, body = render_mention_email(
            branding,
            {
                "author_name": author_name,
                "entity_label": entity_label or entity_type.rstrip("s"),
                "entity_url": deep_link,
                "content_snippet": content_snippet,
            },
        )
        await _queue_notification_email(
            db,
            user_id=mentioned_user_id,
            event_type="mention",
            subject=subject,
            body_html=body,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    return notif


async def notify_on_activity_due(
    db: AsyncSession,
    user_id: int,
    activity_id: int,
    activity_subject: str,
    *,
    activity_due_at: str | None = None,
    entity_label: str | None = None,
) -> Notification | None:
    """Create a notification when an activity is due.

    ``activity_due_at`` (preformatted) and ``entity_label`` populate the
    email body when provided. Older callers that pass only the legacy
    arguments still get the in-app notification and a slimmer email.
    """
    notif: Notification | None = None
    if await should_notify_in_app(db, user_id, "task_due"):
        service = NotificationService(db)
        notif = await service.create_notification(
            user_id=user_id,
            type="activity_due",
            title="Activity due",
            message=f'Activity "{activity_subject}" is due soon',
            entity_type="activities",
            entity_id=activity_id,
        )

    if await should_send_email(db, user_id, "task_due"):
        from src.email.branded_templates import (
            TenantBrandingHelper,
            render_task_due_email,
        )

        branding = await TenantBrandingHelper.get_branding_for_user(db, user_id)
        deep_link = _deep_link("activities", activity_id)
        subject, body = render_task_due_email(
            branding,
            {
                "activity_subject": activity_subject,
                "activity_due_at": activity_due_at or "",
                "activity_url": deep_link,
                "entity_label": entity_label or "",
            },
        )
        await _queue_notification_email(
            db,
            user_id=user_id,
            event_type="task_due",
            subject=subject,
            body_html=body,
            entity_type="activities",
            entity_id=activity_id,
        )
    return notif


async def notify_on_email_reply_received(
    db: AsyncSession,
    *,
    recipient_user_id: int,
    contact_id: int,
    sender_email: str,
    sender_name: str | None,
    subject_line: str,
    snippet: str,
    participant_emails: list[str] | None = None,
) -> Notification | None:
    """Notify a participant user when an inbound email reply lands.

    Fired by the Gmail sync worker after :func:`_store_inbound`
    successfully links an inbound message to a CRM contact AND the
    inbound carries a literal ``In-Reply-To`` header (so this is a
    reply to a thread the CRM is on, not arbitrary cold inbound).

    The deep link points at the contact detail page's email tab; the
    front-end will scroll to the latest message.
    """
    if participant_emails:
        from src.email.participants import get_user_connection_emails

        user_addrs = set(await get_user_connection_emails(db, recipient_user_id))
        if not user_addrs.intersection(a.lower() for a in participant_emails):
            logger.warning(
                "notify_on_email_reply_received: user %s not in participant_emails — skipping",
                recipient_user_id,
            )
            return None

    notif: Notification | None = None
    if await should_notify_in_app(db, recipient_user_id, "email_reply_received"):
        service = NotificationService(db)
        display_name = sender_name or sender_email or "A contact"
        truncated = snippet[:200] if snippet else ""
        notif = await service.create_notification(
            user_id=recipient_user_id,
            type="email_reply",
            title=f"Reply from {display_name}",
            message=f'"{subject_line}" — {truncated}' if truncated else f'"{subject_line}"',
            entity_type="contacts",
            entity_id=contact_id,
        )

    if await should_send_email(db, recipient_user_id, "email_reply_received"):
        from src.email.branded_templates import (
            TenantBrandingHelper,
            render_email_reply_email,
        )

        branding = await TenantBrandingHelper.get_branding_for_user(
            db, recipient_user_id,
        )
        deep_link = _deep_link("contacts", contact_id, suffix="?tab=emails")
        subject, body = render_email_reply_email(
            branding,
            {
                "sender_email": sender_email,
                "sender_name": sender_name or "",
                "subject_line": subject_line,
                "snippet": snippet,
                "thread_url": deep_link,
            },
        )
        await _queue_notification_email(
            db,
            user_id=recipient_user_id,
            event_type="email_reply_received",
            subject=subject,
            body_html=body,
            entity_type="contacts",
            entity_id=contact_id,
        )
    return notif


async def notify_on_proposal_signed(
    db: AsyncSession,
    *,
    owner_id: int,
    proposal_id: int,
    proposal_title: str,
    signer_name: str | None,
    signed_at: str | None,
) -> Notification | None:
    """Notify the proposal owner when their proposal is countersigned.

    Distinct from the always-on signer-side ``send_signed_copy_to_client``
    which mails the signer their PDF — this is the matrix-gated
    in-app + email notification to the internal owner.
    """
    notif: Notification | None = None
    if await should_notify_in_app(db, owner_id, "proposal_signed"):
        service = NotificationService(db)
        notif = await service.create_notification(
            user_id=owner_id,
            type="proposal_signed",
            title="Proposal signed",
            message=f'"{proposal_title}" was signed by {signer_name or "the client"}',
            entity_type="proposals",
            entity_id=proposal_id,
        )

    if await should_send_email(db, owner_id, "proposal_signed"):
        from src.email.branded_templates import (
            TenantBrandingHelper,
            render_proposal_signed_email,
        )

        branding = await TenantBrandingHelper.get_branding_for_user(db, owner_id)
        deep_link = _deep_link("proposals", proposal_id)
        subject, body = render_proposal_signed_email(
            branding,
            {
                "proposal_title": proposal_title,
                "signer_name": signer_name or "",
                "signed_at": signed_at or "",
                "proposal_url": deep_link,
            },
        )
        await _queue_notification_email(
            db,
            user_id=owner_id,
            event_type="proposal_signed",
            subject=subject,
            body_html=body,
            entity_type="proposals",
            entity_id=proposal_id,
        )
    return notif


async def notify_on_contract_signed(
    db: AsyncSession,
    *,
    owner_id: int,
    contract_id: int,
    contract_title: str,
    signer_name: str | None,
    signed_at: str | None,
) -> Notification | None:
    """Notify the contract owner when their contract is countersigned.

    Distinct from the always-on signer-side
    :func:`ContractService._send_signed_copy` which mails the signer
    their PDF — this is the matrix-gated owner-side notification.
    """
    notif: Notification | None = None
    if await should_notify_in_app(db, owner_id, "contract_signed"):
        service = NotificationService(db)
        notif = await service.create_notification(
            user_id=owner_id,
            type="contract_signed",
            title="Contract signed",
            message=f'"{contract_title}" was signed by {signer_name or "the client"}',
            entity_type="contracts",
            entity_id=contract_id,
        )

    if await should_send_email(db, owner_id, "contract_signed"):
        from src.email.branded_templates import (
            TenantBrandingHelper,
            render_contract_signed_email,
        )

        branding = await TenantBrandingHelper.get_branding_for_user(db, owner_id)
        deep_link = _deep_link("contracts", contract_id)
        subject, body = render_contract_signed_email(
            branding,
            {
                "audience": "owner",
                "contract_title": contract_title,
                "signer_name": signer_name or "",
                "signed_at": signed_at or "",
                "contract_url": deep_link,
            },
        )
        await _queue_notification_email(
            db,
            user_id=owner_id,
            event_type="contract_signed",
            subject=subject,
            body_html=body,
            entity_type="contracts",
            entity_id=contract_id,
        )
    return notif


async def notify_admins_of_pending_user(db: AsyncSession, user: User) -> None:
    """Notify every active admin that a new user is awaiting approval.

    Best-effort: a failure to create a single notification is logged and
    swallowed so it can't abort the sign-up transaction (which would
    silently rollback the newly-created user row and leave the requester
    stuck in a retry loop).
    """
    result = await db.execute(
        select(User).where(
            (User.is_superuser == True) | (User.role == "admin"),
            User.is_active == True,
        )
    )
    admins = result.scalars().all()
    service = NotificationService(db)
    for admin in admins:
        try:
            await service.create_notification(
                user_id=admin.id,
                type="pending_approval",
                title="New access request",
                message=f"New access request: {user.full_name} ({user.email})",
                entity_type="users",
                entity_id=user.id,
            )
        except Exception:
            logger.exception(
                "Failed to notify admin %s of pending user %s",
                admin.id,
                user.id,
            )

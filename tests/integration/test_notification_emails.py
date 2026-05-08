"""Integration tests for the email-gating side of the 6 notification dispatchers.

Each test class exercises one dispatcher. We verify:
  - default prefs → EmailQueue row is created with the expected subject/recipient
  - per-event email disabled → no EmailQueue row
  - master email switch off → no EmailQueue row (first dispatcher only)
  - in-app notification still fires when email is off (where applicable)

No mocks — real SQLite in-memory session via the conftest fixtures.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.account.service import AccountPrefsService
from src.account.schemas import NotificationPrefsUpdate
from src.auth.models import User
from src.email.models import EmailQueue
from src.notifications.models import Notification
from src.notifications.service import (
    notify_on_assignment,
    notify_on_activity_due,
    notify_on_mention,
    notify_on_email_reply_received,
    notify_on_proposal_signed,
    notify_on_contract_signed,
)


async def _email_rows(db: AsyncSession, user_id: int) -> list[EmailQueue]:
    result = await db.execute(
        select(EmailQueue).where(EmailQueue.sent_by_id == user_id)
    )
    return list(result.scalars().all())


async def _notif_rows(db: AsyncSession, user_id: int) -> list[Notification]:
    result = await db.execute(
        select(Notification).where(Notification.user_id == user_id)
    )
    return list(result.scalars().all())


async def _disable_email_event(db: AsyncSession, user_id: int, event_key: str) -> None:
    svc = AccountPrefsService(db)
    await svc.update_notification_prefs(
        user_id,
        NotificationPrefsUpdate(event_matrix={event_key: {"email": False}}),
    )


# ---------------------------------------------------------------------------
# 1. notify_on_assignment
# ---------------------------------------------------------------------------


class TestNotifyOnAssignmentEmail:
    async def test_email_queued_when_prefs_allow(
        self, db_session: AsyncSession, test_user: User
    ):
        """Default prefs → EmailQueue row to test_user.email with correct subject."""
        await notify_on_assignment(
            db_session,
            test_user.id,
            "leads",
            42,
            "Jane Cooper",
            entity_email="jane@x.com",
            entity_company="Cooper LLC",
            assigner_name="Daisy",
        )
        rows = await _email_rows(db_session, test_user.id)
        assert len(rows) == 1
        assert rows[0].to_email == test_user.email
        assert "New lead assigned: Jane Cooper" in rows[0].subject
        assert "/leads/42" in rows[0].body

    async def test_email_skipped_when_prefs_disable(
        self, db_session: AsyncSession, test_user: User
    ):
        """event_matrix lead_assigned email=False → no EmailQueue row."""
        await _disable_email_event(db_session, test_user.id, "lead_assigned")
        await notify_on_assignment(
            db_session,
            test_user.id,
            "leads",
            42,
            "Jane Cooper",
            assigner_name="Daisy",
        )
        rows = await _email_rows(db_session, test_user.id)
        assert rows == []

    async def test_inapp_still_fires_when_email_off(
        self, db_session: AsyncSession, test_user: User
    ):
        """In-app notification row is created even when email is disabled."""
        await _disable_email_event(db_session, test_user.id, "lead_assigned")
        await notify_on_assignment(
            db_session,
            test_user.id,
            "leads",
            42,
            "Jane Cooper",
        )
        notifs = await _notif_rows(db_session, test_user.id)
        assert len(notifs) == 1

    async def test_email_skipped_when_master_email_off(
        self, db_session: AsyncSession, test_user: User
    ):
        """email_enabled=False master switch → no EmailQueue row."""
        svc = AccountPrefsService(db_session)
        await svc.update_notification_prefs(
            test_user.id,
            NotificationPrefsUpdate(email_enabled=False),
        )
        await notify_on_assignment(
            db_session,
            test_user.id,
            "leads",
            42,
            "Jane Cooper",
        )
        rows = await _email_rows(db_session, test_user.id)
        assert rows == []


# ---------------------------------------------------------------------------
# 2. notify_on_activity_due
# ---------------------------------------------------------------------------


class TestNotifyOnActivityDueEmail:
    async def test_email_queued(self, db_session: AsyncSession, test_user: User):
        """Default prefs → EmailQueue row with task-due subject."""
        await notify_on_activity_due(
            db_session,
            test_user.id,
            7,
            "Follow up on demo",
            activity_due_at="Friday May 8",
            entity_label="Cooper LLC · Jane",
        )
        rows = await _email_rows(db_session, test_user.id)
        assert len(rows) == 1
        assert rows[0].subject == "Task due — Follow up on demo"
        assert rows[0].to_email == test_user.email

    async def test_email_skipped_when_disabled(
        self, db_session: AsyncSession, test_user: User
    ):
        """event_matrix task_due email=False → no EmailQueue row."""
        await _disable_email_event(db_session, test_user.id, "task_due")
        await notify_on_activity_due(
            db_session,
            test_user.id,
            7,
            "Follow up on demo",
            activity_due_at="Friday May 8",
        )
        rows = await _email_rows(db_session, test_user.id)
        assert rows == []


# ---------------------------------------------------------------------------
# 3. notify_on_mention
# ---------------------------------------------------------------------------


class TestNotifyOnMentionEmail:
    async def test_email_queued(self, db_session: AsyncSession, test_user: User):
        """Default prefs → EmailQueue row with mention subject."""
        await notify_on_mention(
            db_session,
            test_user.id,
            "Daisy Mentions",
            "contacts",
            7,
            "Big juicy comment",
            entity_label="Acme",
        )
        rows = await _email_rows(db_session, test_user.id)
        assert len(rows) == 1
        assert "Daisy Mentions mentioned you on Acme" in rows[0].subject
        assert rows[0].to_email == test_user.email

    async def test_email_skipped_when_disabled(
        self, db_session: AsyncSession, test_user: User
    ):
        """event_matrix mention email=False → no EmailQueue row."""
        await _disable_email_event(db_session, test_user.id, "mention")
        await notify_on_mention(
            db_session,
            test_user.id,
            "Daisy Mentions",
            "contacts",
            7,
            "Big juicy comment",
            entity_label="Acme",
        )
        rows = await _email_rows(db_session, test_user.id)
        assert rows == []


# ---------------------------------------------------------------------------
# 4. notify_on_email_reply_received
# ---------------------------------------------------------------------------


class TestNotifyOnEmailReplyReceivedEmail:
    async def test_email_queued(self, db_session: AsyncSession, test_user: User):
        """Default prefs → EmailQueue row with reply-received subject."""
        await notify_on_email_reply_received(
            db_session,
            recipient_user_id=test_user.id,
            contact_id=42,
            sender_email="x@y.com",
            sender_name="Big Client",
            subject_line="Re: Thing",
            snippet="Looks great",
        )
        rows = await _email_rows(db_session, test_user.id)
        assert len(rows) == 1
        assert rows[0].subject == "Reply received — Re: Thing"
        assert rows[0].to_email == test_user.email

    async def test_email_skipped_when_disabled(
        self, db_session: AsyncSession, test_user: User
    ):
        """event_matrix email_reply_received email=False → no EmailQueue row."""
        await _disable_email_event(db_session, test_user.id, "email_reply_received")
        await notify_on_email_reply_received(
            db_session,
            recipient_user_id=test_user.id,
            contact_id=42,
            sender_email="x@y.com",
            sender_name="Big Client",
            subject_line="Re: Thing",
            snippet="Looks great",
        )
        rows = await _email_rows(db_session, test_user.id)
        assert rows == []

    async def test_inapp_creates_notification_row(
        self, db_session: AsyncSession, test_user: User
    ):
        """In-app notification row created for email reply event."""
        await notify_on_email_reply_received(
            db_session,
            recipient_user_id=test_user.id,
            contact_id=42,
            sender_email="x@y.com",
            sender_name="Big Client",
            subject_line="Re: Thing",
            snippet="Looks great",
        )
        notifs = await _notif_rows(db_session, test_user.id)
        assert len(notifs) == 1
        assert notifs[0].type == "email_reply"


# ---------------------------------------------------------------------------
# 5. notify_on_proposal_signed
# ---------------------------------------------------------------------------


class TestNotifyOnProposalSignedEmail:
    async def test_email_queued(self, db_session: AsyncSession, test_user: User):
        """Default prefs → EmailQueue row with proposal-signed subject."""
        await notify_on_proposal_signed(
            db_session,
            owner_id=test_user.id,
            proposal_id=9,
            proposal_title="Q3 Engagement",
            signer_name="Jane Cooper",
            signed_at="May 7 14:23 UTC",
        )
        rows = await _email_rows(db_session, test_user.id)
        assert len(rows) == 1
        assert rows[0].subject == "Proposal signed — Q3 Engagement"
        assert rows[0].to_email == test_user.email

    async def test_email_skipped_when_disabled(
        self, db_session: AsyncSession, test_user: User
    ):
        """event_matrix proposal_signed email=False → no EmailQueue row."""
        await _disable_email_event(db_session, test_user.id, "proposal_signed")
        await notify_on_proposal_signed(
            db_session,
            owner_id=test_user.id,
            proposal_id=9,
            proposal_title="Q3 Engagement",
            signer_name="Jane Cooper",
            signed_at="May 7 14:23 UTC",
        )
        rows = await _email_rows(db_session, test_user.id)
        assert rows == []


# ---------------------------------------------------------------------------
# 6. notify_on_contract_signed
# ---------------------------------------------------------------------------


class TestNotifyOnContractSignedEmail:
    async def test_email_queued(self, db_session: AsyncSession, test_user: User):
        """Default prefs → EmailQueue row with contract-signed subject."""
        await notify_on_contract_signed(
            db_session,
            owner_id=test_user.id,
            contract_id=42,
            contract_title="MSA 2026",
            signer_name="Jane Cooper",
            signed_at="May 7 14:23 UTC",
        )
        rows = await _email_rows(db_session, test_user.id)
        assert len(rows) == 1
        assert rows[0].subject == "Contract signed — MSA 2026"
        assert rows[0].to_email == test_user.email

    async def test_email_skipped_when_disabled(
        self, db_session: AsyncSession, test_user: User
    ):
        """event_matrix contract_signed email=False → no EmailQueue row."""
        await _disable_email_event(db_session, test_user.id, "contract_signed")
        await notify_on_contract_signed(
            db_session,
            owner_id=test_user.id,
            contract_id=42,
            contract_title="MSA 2026",
            signer_name="Jane Cooper",
            signed_at="May 7 14:23 UTC",
        )
        rows = await _email_rows(db_session, test_user.id)
        assert rows == []

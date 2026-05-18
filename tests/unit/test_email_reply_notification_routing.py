"""Integration tests for email-reply notification routing.

Verifies that inbound-reply notifications are sent only to users who
appear in the message's To/CC headers — NOT to the contact owner when
they aren't a participant (the privacy leak fixed in this PR).
"""

import os
import sys
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from src.account.models import UserNotificationPrefs
from src.auth.models import User
from src.auth.security import get_password_hash
from src.contacts.models import Contact
from src.database import Base
from src.integrations.gmail.models import GmailConnection
from src.notifications.models import Notification

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncSession:
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()


async def _make_user(db: AsyncSession, email: str, *, is_superuser: bool = False) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash("pw"),
        full_name=email.split("@")[0],
        is_active=True,
        is_superuser=is_superuser,
    )
    db.add(user)
    await db.flush()
    return user


async def _enable_notifications(db: AsyncSession, user: User) -> None:
    prefs = UserNotificationPrefs(
        user_id=user.id,
        in_app_enabled=True,
        email_enabled=True,
        event_matrix={"email_reply_received": {"in_app": True, "email": True}},
    )
    db.add(prefs)
    await db.flush()


async def _make_connection(db: AsyncSession, user_id: int, email: str) -> GmailConnection:
    conn = GmailConnection(
        user_id=user_id,
        email=email,
        access_token="tok",
        scopes="https://mail.google.com/",
    )
    db.add(conn)
    await db.flush()
    return conn


def _make_inbound_msg(
    *,
    msg_id: str,
    from_: str,
    to: str,
    cc: str | None = None,
    thread_id: str = "thread-001",
    in_reply_to: str | None = "<original@example.com>",
    subject: str = "Re: Test",
    body: str = "Reply body",
) -> dict:
    """Build a parsed-message dict that mirrors what GmailClient._parse_message returns."""
    to_list = [a.strip() for a in to.split(",") if a.strip()]
    cc_list = [a.strip() for a in cc.split(",") if a.strip()] if cc else []
    return {
        "message_id": msg_id,
        "thread_id": thread_id,
        "from": from_,
        "from_header": from_,
        "to": to,
        "to_list": to_list,
        "cc": cc,
        "cc_list": cc_list,
        "bcc": None,
        "bcc_list": [],
        "subject": subject,
        "body_text": body,
        "body_html": None,
        "date": datetime.now(UTC),
        "in_reply_to": in_reply_to,
        "attachments": [],
        "raw_payload": {"id": msg_id},
    }


class TestEmailReplyNotificationRouting:
    @pytest.mark.asyncio
    async def test_only_participant_notified_not_contact_owner(self, db: AsyncSession):
        """Notification goes to To: recipient (S), NOT to contact owner (A) who isn't on the thread."""
        admin = await _make_user(db, "admin@crm.com", is_superuser=True)
        sales = await _make_user(db, "sales@crm.com")
        other = await _make_user(db, "other@crm.com")

        await _make_connection(db, admin.id, "admin@crm.com")
        sales_conn = await _make_connection(db, sales.id, "sales@crm.com")
        await _make_connection(db, other.id, "other@crm.com")

        # Contact is owned by admin but the inbound is addressed to sales only
        contact = Contact(
            first_name="Client",
            last_name="Person",
            email="client@external.com",
            owner_id=admin.id,
        )
        db.add(contact)
        await db.flush()

        # Only sales is opted in — admin is intentionally not opted in to prove they're excluded
        await _enable_notifications(db, sales)
        await db.commit()

        from src.integrations.gmail.sync import _store_inbound

        msg = _make_inbound_msg(
            msg_id="<inbound-001@gmail.com>",
            from_="client@external.com",
            to="sales@crm.com",
        )
        await _store_inbound(msg, sales_conn, db, datetime.now(UTC))
        await db.commit()

        notifs = (await db.execute(select(Notification))).scalars().all()
        notified_ids = {n.user_id for n in notifs if n.type == "email_reply"}

        assert sales.id in notified_ids, "Sales rep (To: participant) should be notified"
        assert admin.id not in notified_ids, "Admin (contact owner, not on thread) must NOT be notified"
        assert other.id not in notified_ids, "Other rep (unrelated) must NOT be notified"

    @pytest.mark.asyncio
    async def test_cc_participant_also_notified(self, db: AsyncSession):
        """When admin is CC'd, both the To: recipient and CC: admin receive notifications."""
        admin = await _make_user(db, "admin@crm.com", is_superuser=True)
        sales = await _make_user(db, "sales@crm.com")

        await _make_connection(db, admin.id, "admin@crm.com")
        sales_conn = await _make_connection(db, sales.id, "sales@crm.com")

        contact = Contact(
            first_name="Client",
            last_name="Person",
            email="client@external.com",
            owner_id=admin.id,
        )
        db.add(contact)
        await db.flush()

        await _enable_notifications(db, admin)
        await _enable_notifications(db, sales)
        await db.commit()

        from src.integrations.gmail.sync import _store_inbound

        msg = _make_inbound_msg(
            msg_id="<inbound-002@gmail.com>",
            from_="client@external.com",
            to="sales@crm.com",
            cc="admin@crm.com",
        )
        # Use sales_conn as the receiving account (doesn't matter for inbound routing)
        await _store_inbound(msg, sales_conn, db, datetime.now(UTC))
        await db.commit()

        notifs = (await db.execute(select(Notification))).scalars().all()
        notified_ids = {n.user_id for n in notifs if n.type == "email_reply"}

        assert sales.id in notified_ids, "Sales rep (To: participant) should be notified"
        assert admin.id in notified_ids, "Admin (CC: participant) should be notified"

    @pytest.mark.asyncio
    async def test_null_owner_still_notifies_participant(self, db: AsyncSession):
        """Contact with no owner should not block notification to actual email participant."""
        sales = await _make_user(db, "sales@crm.com")
        sales_conn = await _make_connection(db, sales.id, "sales@crm.com")

        # Contact with owner_id=None
        contact = Contact(
            first_name="Client",
            last_name="Noowner",
            email="client@external.com",
            owner_id=None,
        )
        db.add(contact)
        await db.flush()
        await _enable_notifications(db, sales)
        await db.commit()

        from src.integrations.gmail.sync import _store_inbound

        msg = _make_inbound_msg(
            msg_id="<inbound-003@gmail.com>",
            from_="client@external.com",
            to="sales@crm.com",
        )
        await _store_inbound(msg, sales_conn, db, datetime.now(UTC))
        await db.commit()

        notifs = (await db.execute(select(Notification))).scalars().all()
        notified_ids = {n.user_id for n in notifs if n.type == "email_reply"}

        assert sales.id in notified_ids, "Sales rep should get notification even when contact has no owner"


class TestNotificationGuardDirect:
    @pytest.mark.asyncio
    async def test_guard_skips_when_recipient_not_on_message(self, db: AsyncSession):
        """notify_on_email_reply_received returns None when recipient's email isn't in participant_emails."""
        user = await _make_user(db, "unrelated@crm.com")
        await _make_connection(db, user.id, "unrelated@crm.com")
        contact = Contact(
            first_name="Client", last_name="X", email="client@external.com", owner_id=user.id
        )
        db.add(contact)
        await db.flush()
        await db.commit()

        from src.notifications.service import notify_on_email_reply_received

        result = await notify_on_email_reply_received(
            db=db,
            recipient_user_id=user.id,
            contact_id=contact.id,
            sender_email="client@external.com",
            sender_name="Client",
            subject_line="Re: Hello",
            snippet="body",
            # Participant list does NOT include the recipient's address
            participant_emails=["sales@crm.com", "client@external.com"],
        )

        assert result is None, "Guard must return None when recipient address is absent from participant_emails"
        notifs = (await db.execute(select(Notification))).scalars().all()
        assert not any(n.user_id == user.id for n in notifs), "No in-app notification should be created"

    @pytest.mark.asyncio
    async def test_guard_allows_when_recipient_is_participant(self, db: AsyncSession):
        """notify_on_email_reply_received creates notification when recipient is in participant_emails."""
        user = await _make_user(db, "rep@crm.com")
        await _make_connection(db, user.id, "rep@crm.com")
        contact = Contact(
            first_name="Client", last_name="Y", email="client@external.com", owner_id=user.id
        )
        db.add(contact)
        await db.flush()
        await _enable_notifications(db, user)
        await db.commit()

        from src.notifications.service import notify_on_email_reply_received

        result = await notify_on_email_reply_received(
            db=db,
            recipient_user_id=user.id,
            contact_id=contact.id,
            sender_email="client@external.com",
            sender_name="Client",
            subject_line="Re: Hello",
            snippet="body",
            participant_emails=["rep@crm.com", "client@external.com"],
        )

        assert result is not None, "Notification should be created when recipient is a participant"

    @pytest.mark.asyncio
    async def test_no_notification_when_message_has_no_in_reply_to(self, db: AsyncSession):
        """Cold inbound (no In-Reply-To header) must never trigger a reply notification."""
        sales = await _make_user(db, "sales@crm.com")
        sales_conn = await _make_connection(db, sales.id, "sales@crm.com")
        contact = Contact(
            first_name="Client", last_name="Cold", email="cold@external.com", owner_id=sales.id
        )
        db.add(contact)
        await db.flush()
        await db.commit()

        from src.integrations.gmail.sync import _store_inbound

        msg = _make_inbound_msg(
            msg_id="<cold-inbound-001@gmail.com>",
            from_="cold@external.com",
            to="sales@crm.com",
            in_reply_to=None,  # cold inbound — no In-Reply-To header
        )
        await _store_inbound(msg, sales_conn, db, datetime.now(UTC))
        await db.commit()

        notifs = (await db.execute(select(Notification))).scalars().all()
        assert not any(n.type == "email_reply" for n in notifs), (
            "Cold inbound (no In-Reply-To) must not fire email_reply notification"
        )


class TestGuardEdgeCases:
    @pytest.mark.asyncio
    async def test_guard_skips_on_empty_participant_list(self, db: AsyncSession):
        """Guard returns None when participant_emails=[] (caller bug path, not a real skip)."""
        user = await _make_user(db, "rep@crm.com")
        await _make_connection(db, user.id, "rep@crm.com")
        contact = Contact(first_name="C", last_name="D", email="c@ext.com", owner_id=user.id)
        db.add(contact)
        await db.flush()
        await db.commit()

        from src.notifications.service import notify_on_email_reply_received

        result = await notify_on_email_reply_received(
            db=db,
            recipient_user_id=user.id,
            contact_id=contact.id,
            sender_email="c@ext.com",
            sender_name="C",
            subject_line="Re: Hi",
            snippet="body",
            participant_emails=[],  # empty — distinct from None
        )
        assert result is None, "Empty participant_emails must short-circuit to None"

    @pytest.mark.asyncio
    async def test_guard_skips_when_user_has_no_active_connection(self, db: AsyncSession):
        """Guard returns None when the recipient has no active Gmail connection."""

        from src.integrations.gmail.models import GmailConnection as _GC

        user = await _make_user(db, "noconn@crm.com")
        # Revoked connection — not active
        revoked = _GC(
            user_id=user.id,
            email="noconn@crm.com",
            access_token="tok",
            scopes="https://mail.google.com/",
            revoked_at=datetime.now(UTC),
        )
        db.add(revoked)
        contact = Contact(first_name="E", last_name="F", email="e@ext.com", owner_id=user.id)
        db.add(contact)
        await db.flush()
        await db.commit()

        from src.notifications.service import notify_on_email_reply_received

        result = await notify_on_email_reply_received(
            db=db,
            recipient_user_id=user.id,
            contact_id=contact.id,
            sender_email="e@ext.com",
            sender_name="E",
            subject_line="Re: Hi",
            snippet="body",
            participant_emails=["noconn@crm.com", "e@ext.com"],
        )
        assert result is None, "User with no active connection must not receive notification"


class TestAliasParticipantPath:
    @pytest.mark.asyncio
    async def test_alias_user_matched_and_passes_guard(self, db: AsyncSession):
        """User matched via send-as alias must both be found by resolver and pass the guard.

        This is the bug the trio block caught: find_user_ids_by_addresses matched
        on aliases (Postgres) but get_user_connection_emails only returned primary
        email, so the guard would log-warn and drop the notification for alias users.
        """
        user = await _make_user(db, "giancarlo@crm.com")
        # Primary connection email differs from the alias the client emailed
        conn = GmailConnection(
            user_id=user.id,
            email="giancarlo@crm.com",
            aliases=["giancarlo@linkcreativeco.com"],
            access_token="tok",
            scopes="https://mail.google.com/",
        )
        db.add(conn)

        contact = Contact(
            first_name="Client",
            last_name="Alias",
            email="client@external.com",
            owner_id=None,
        )
        db.add(contact)
        await db.flush()
        await _enable_notifications(db, user)
        await db.commit()

        from src.email.participants import get_user_connection_emails
        from src.notifications.service import notify_on_email_reply_received

        # Verify the helper now returns both primary and alias
        addrs = await get_user_connection_emails(db, user.id)
        assert "giancarlo@crm.com" in addrs
        assert "giancarlo@linkcreativeco.com" in addrs

        # Guard must pass when participant_emails contains the alias address
        result = await notify_on_email_reply_received(
            db=db,
            recipient_user_id=user.id,
            contact_id=contact.id,
            sender_email="client@external.com",
            sender_name="Client",
            subject_line="Re: Proposal",
            snippet="Looks great",
            participant_emails=["giancarlo@linkcreativeco.com", "client@external.com"],
        )

        assert result is not None, (
            "Notification must fire when recipient is matched via send-as alias"
        )


class TestDeepLinkTabSuffix:
    def test_email_reply_deep_link_uses_emails_plural(self):
        """The deep-link suffix must be '?tab=emails' to match frontend TabType."""
        import re

        with open(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "backend",
                "src",
                "notifications",
                "service.py",
            )
        ) as f:
            source = f.read()

        # The only tab-suffixed deep link is the email-reply one
        match = re.search(r'_deep_link\("contacts".*?suffix="(\?tab=[^"]+)"', source)
        assert match is not None, "_deep_link with contacts suffix not found"
        assert match.group(1) == "?tab=emails", (
            f"Deep link suffix is '{match.group(1)}' but frontend TabType uses '?tab=emails'"
        )

"""Unit tests for reply-threading helpers and inbound contact matching.

Covers:
- `_resolve_reply_context` returns the exact email's thread/message IDs when
  the caller passes a reply target.
- A fresh compose (no `reply_to_*` set) returns `(None, None)` so the new
  message starts its own Gmail thread instead of silently inheriting the
  newest unrelated message on the contact.
- `_store_inbound` matches contacts case-insensitively.
"""

import os
import sys
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from src.auth.models import User
from src.companies.models import Company
from src.contacts.models import Contact
from src.database import Base
from src.email.models import EmailQueue, InboundEmail
from src.email.service import _resolve_reply_context
from src.integrations.gmail.models import GmailConnection
from src.integrations.gmail.sync import _store_inbound
from ._engine import is_postgres, make_test_engine


@pytest_asyncio.fixture
async def engine():
    eng = make_test_engine()
    async with eng.begin() as conn:
        if is_postgres():
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
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


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    from src.auth.security import get_password_hash
    u = User(
        email="owner@example.com",
        hashed_password=get_password_hash("pw"),
        full_name="Owner",
        is_active=True,
        is_superuser=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def contact(db: AsyncSession, user: User) -> Contact:
    co = Company(name="Acme", owner_id=user.id)
    db.add(co)
    await db.commit()
    c = Contact(
        first_name="Harsh",
        last_name="V",
        email="Contact@Example.COM",
        company_id=co.id,
        owner_id=user.id,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@pytest_asyncio.fixture
async def connection(db: AsyncSession, user: User) -> GmailConnection:
    conn = GmailConnection(
        user_id=user.id,
        email="mailbox@example.com",
        access_token="tok",
        refresh_token="rtok",
        token_expiry=datetime.now(UTC) + timedelta(hours=1),
        scopes="https://mail.google.com/",
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return conn


# ---------------------------------------------------------------------------
# _resolve_reply_context
# ---------------------------------------------------------------------------

class TestResolveReplyContext:
    @pytest.mark.asyncio
    async def test_returns_outbound_thread_and_message_ids(self, db, contact, user):
        row = EmailQueue(
            to_email="x@y.com",
            subject="s",
            body="b",
            sent_by_id=user.id,
            entity_type="contacts",
            entity_id=contact.id,
            message_id="<m1@gmail>",
            thread_id="thread-1",
            status="sent",
            attempts=1,
        )
        db.add(row)
        await db.commit()

        thread, message = await _resolve_reply_context(
            db,
            reply_to_email_id=row.id,
            reply_to_inbound_id=None,
            entity_type="contacts",
            entity_id=contact.id,
            sent_by_id=user.id,
        )
        assert thread == "thread-1"
        assert message == "<m1@gmail>"

    @pytest.mark.asyncio
    async def test_returns_inbound_thread_and_message_ids(self, db, contact):
        row = InboundEmail(
            resend_email_id="rid-1",
            from_email="them@example.com",
            to_email="us@example.com",
            subject="s",
            message_id="<in1@gmail>",
            thread_id="thread-in",
            received_at=datetime.now(UTC),
            entity_type="contacts",
            entity_id=contact.id,
        )
        db.add(row)
        await db.commit()

        thread, message = await _resolve_reply_context(
            db,
            reply_to_email_id=None,
            reply_to_inbound_id=row.id,
            entity_type="contacts",
            entity_id=contact.id,
        )
        assert thread == "thread-in"
        assert message == "<in1@gmail>"

    @pytest.mark.asyncio
    async def test_returns_none_when_nothing_supplied(self, db):
        assert await _resolve_reply_context(
            db, reply_to_email_id=None, reply_to_inbound_id=None
        ) == (None, None)

    @pytest.mark.asyncio
    async def test_missing_id_returns_none(self, db, contact):
        assert await _resolve_reply_context(
            db,
            reply_to_email_id=99999,
            reply_to_inbound_id=None,
            entity_type="contacts",
            entity_id=contact.id,
        ) == (None, None)

    @pytest.mark.asyncio
    async def test_outbound_rejected_when_entity_mismatches(self, db, contact, user):
        # Row belongs to `contact`, but the outgoing email claims a different entity.
        # Scoping must prevent the metadata from leaking.
        row = EmailQueue(
            to_email="x@y.com",
            subject="s",
            body="b",
            sent_by_id=user.id,
            entity_type="contacts",
            entity_id=contact.id,
            message_id="<m1@gmail>",
            thread_id="thread-1",
            status="sent",
            attempts=1,
        )
        db.add(row)
        await db.commit()

        assert await _resolve_reply_context(
            db,
            reply_to_email_id=row.id,
            reply_to_inbound_id=None,
            entity_type="contacts",
            entity_id=contact.id + 5000,
            sent_by_id=user.id,
        ) == (None, None)

    @pytest.mark.asyncio
    async def test_outbound_targeting_other_senders_row_returns_none(
        self, db, contact, user
    ):
        # User B targets user A's EmailQueue row. Scoping rejects the
        # direct hit (sender mismatch), and there's no implicit fallback
        # any more — fresh compose must NOT inherit a peer's thread.
        other_user_row = EmailQueue(
            to_email="x@y.com",
            subject="other",
            body="b",
            sent_by_id=user.id,
            entity_type="contacts",
            entity_id=contact.id,
            message_id="<user-a@gmail>",
            thread_id="thread-a",
            created_at=datetime.now(UTC) - timedelta(days=1),
            status="sent",
            attempts=1,
        )
        own_row = EmailQueue(
            to_email="x@y.com",
            subject="own",
            body="b",
            sent_by_id=user.id + 9999,
            entity_type="contacts",
            entity_id=contact.id,
            message_id="<user-b@gmail>",
            thread_id="thread-b",
            created_at=datetime.now(UTC),
            status="sent",
            attempts=1,
        )
        db.add_all([other_user_row, own_row])
        await db.commit()

        assert await _resolve_reply_context(
            db,
            reply_to_email_id=other_user_row.id,
            reply_to_inbound_id=None,
            entity_type="contacts",
            entity_id=contact.id,
            sent_by_id=user.id + 9999,
        ) == (None, None)

    @pytest.mark.asyncio
    async def test_fresh_compose_does_not_inherit_prior_thread(
        self, db, contact, user
    ):
        """A compose with no `reply_to_*` must NOT thread on the newest
        prior message. Gmail breaks the thread on the recipient side
        when the subject changes (`Final test with attachment` doesn't
        belong on a `Signed copy — test` thread), so the only effect of
        an implicit fallback was that the CRM thread view stitched
        unrelated messages into one fat card.
        """
        # Pre-populate every kind of prior message — outbound, inbound,
        # different subjects, recent timestamps. None should leak into
        # a fresh compose's reply context.
        db.add_all([
            EmailQueue(
                to_email="x@y.com",
                subject="Signed copy — test",
                body="b",
                sent_by_id=user.id,
                entity_type="contacts",
                entity_id=contact.id,
                message_id="<old-out@gmail>",
                thread_id="thread-stale-out",
                created_at=datetime.now(UTC) - timedelta(minutes=5),
                status="sent",
                attempts=1,
            ),
            InboundEmail(
                resend_email_id="rid-old-in",
                from_email="them@example.com",
                to_email="us@example.com",
                subject="Re: Proposal",
                message_id="<old-in@gmail>",
                thread_id="thread-stale-in",
                received_at=datetime.now(UTC) - timedelta(minutes=2),
                entity_type="contacts",
                entity_id=contact.id,
            ),
        ])
        await db.commit()

        assert await _resolve_reply_context(
            db,
            reply_to_email_id=None,
            reply_to_inbound_id=None,
            entity_type="contacts",
            entity_id=contact.id,
            sent_by_id=user.id,
        ) == (None, None)

    @pytest.mark.asyncio
    async def test_inbound_rejected_when_entity_mismatches(self, db, contact):
        row = InboundEmail(
            resend_email_id="rid-mismatch",
            from_email="them@example.com",
            to_email="us@example.com",
            subject="s",
            message_id="<in1@gmail>",
            thread_id="thread-in",
            received_at=datetime.now(UTC),
            entity_type="contacts",
            entity_id=contact.id,
        )
        db.add(row)
        await db.commit()

        assert await _resolve_reply_context(
            db,
            reply_to_email_id=None,
            reply_to_inbound_id=row.id,
            entity_type="contacts",
            entity_id=contact.id + 5000,
        ) == (None, None)


# ---------------------------------------------------------------------------
# _store_inbound (case-insensitive contact match)
# ---------------------------------------------------------------------------

class TestStoreInboundContactMatch:
    @pytest.mark.asyncio
    async def test_matches_contact_email_case_insensitively(self, db, contact, connection):
        msg = {
            "from": "CONTACT@example.com",  # different case than the stored contact
            "to": connection.email,
            "subject": "hi",
            "body_text": "hello",
            "body_html": None,
            "message_id": "<inbound-1@gmail>",
            "in_reply_to": None,
            "thread_id": "thread-zzz",
            "cc": None,
            "raw_payload": {"id": "g-msg-1"},
        }
        await _store_inbound(msg, connection, db, datetime.now(UTC))
        await db.commit()

        from sqlalchemy import select
        stored = (await db.execute(select(InboundEmail))).scalar_one()
        assert stored.entity_type == "contacts"
        assert stored.entity_id == contact.id

"""
Unit tests for the POST /api/integrations/gmail/relink admin endpoint.

Uses SQLite in-memory DB + httpx.AsyncClient test client (same pattern as
test_gmail_sync.py). find_contact_id_by_any_email is imported from
src.contacts.alias_match (Worker B's module); the import is guarded so
scaffolding compiles even before B pushes.
"""

import base64
import os
import sys
from datetime import UTC, datetime
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from src.auth.dependencies import get_current_active_user, get_current_superuser
from src.auth.models import User
from src.auth.security import get_password_hash
from src.contacts.models import Contact
from src.database import Base, get_db
from src.email.models import EmailQueue, InboundEmail
from src.integrations.gmail.router import router as gmail_router

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    user = User(
        email="admin@example.com",
        hashed_password=get_password_hash("pw"),
        full_name="Admin",
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_user(db: AsyncSession) -> User:
    user = User(
        email="regular@example.com",
        hashed_password=get_password_hash("pw"),
        full_name="Regular",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# FastAPI test app factory
# ---------------------------------------------------------------------------


def _make_app(db_session: AsyncSession, current_user: User) -> FastAPI:
    """Build a minimal FastAPI app with the gmail router and overridden deps."""
    app = FastAPI()
    app.include_router(gmail_router)

    async def _override_db():
        yield db_session

    async def _override_active_user():
        return current_user

    async def _override_superuser():
        from fastapi import HTTPException
        if not current_user.is_superuser and getattr(current_user, "role", "") != "admin":
            raise HTTPException(status_code=403, detail="Not enough privileges")
        return current_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_active_user] = _override_active_user
    app.dependency_overrides[get_current_superuser] = _override_superuser
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRelinkAuth:
    @pytest.mark.asyncio
    async def test_non_admin_gets_403(self, db: AsyncSession, regular_user: User):
        """Non-admin user must receive 403 from the relink endpoint."""
        app = _make_app(db, regular_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/integrations/gmail/relink", json={})
        assert resp.status_code == 403


class TestRelinkEmailQueue:
    @pytest.mark.asyncio
    async def test_null_entity_with_cc_contact_gets_linked(
        self, db: AsyncSession, admin_user: User
    ):
        """EmailQueue row with NULL entity_id whose CC contains a contact email is linked."""
        contact = Contact(
            email="contact@client.com",
            first_name="CC",
            last_name="Contact",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db.add(contact)
        await db.commit()
        await db.refresh(contact)

        row = EmailQueue(
            to_email="someone@other.com",
            from_email="sender@example.com",
            cc="Display Name <contact@client.com>",
            subject="Test",
            body="body",
            status="sent",
            sent_via="gmail",
            sent_by_id=admin_user.id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        app = _make_app(db, admin_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/integrations/gmail/relink", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert data["linked"] == 1
        assert data["scanned"] >= 1
        assert data["dry_run"] is False

        await db.refresh(row)
        assert row.entity_type == "contacts"
        assert row.entity_id == contact.id

    @pytest.mark.asyncio
    async def test_already_linked_row_not_touched(
        self, db: AsyncSession, admin_user: User
    ):
        """EmailQueue row with a non-NULL entity_id must not be overwritten."""
        contact = Contact(
            email="existing@client.com",
            first_name="Existing",
            last_name="Link",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db.add(contact)
        await db.commit()
        await db.refresh(contact)

        row = EmailQueue(
            to_email="existing@client.com",
            from_email="sender@example.com",
            subject="Already linked",
            body="body",
            status="sent",
            sent_via="gmail",
            sent_by_id=admin_user.id,
            entity_type="contacts",
            entity_id=contact.id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        original_entity_id = row.entity_id

        app = _make_app(db, admin_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/integrations/gmail/relink", json={})

        assert resp.status_code == 200
        data = resp.json()
        # Row with entity_id set is excluded by the WHERE clause — not scanned.
        assert data["linked"] == 0

        await db.refresh(row)
        assert row.entity_id == original_entity_id

    @pytest.mark.asyncio
    async def test_no_matching_contact_row_is_skipped(
        self, db: AsyncSession, admin_user: User
    ):
        """EmailQueue row whose addresses match no contact must be skipped (not linked)."""
        row = EmailQueue(
            to_email="unknown@nowhere.com",
            from_email="also@unknown.com",
            subject="No match",
            body="body",
            status="sent",
            sent_via="gmail",
            sent_by_id=admin_user.id,
        )
        db.add(row)
        await db.commit()

        app = _make_app(db, admin_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/integrations/gmail/relink", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert data["linked"] == 0
        assert data["skipped"] >= 1

        await db.refresh(row)
        assert row.entity_id is None

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write(
        self, db: AsyncSession, admin_user: User
    ):
        """dry_run=True must leave entity_id NULL even when a match is found."""
        contact = Contact(
            email="dryrun@client.com",
            first_name="Dry",
            last_name="Run",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db.add(contact)
        await db.commit()
        await db.refresh(contact)

        row = EmailQueue(
            to_email="dryrun@client.com",
            from_email="sender@example.com",
            subject="Dry run test",
            body="body",
            status="sent",
            sent_via="gmail",
            sent_by_id=admin_user.id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        app = _make_app(db, admin_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/integrations/gmail/relink", json={"dry_run": True}
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["dry_run"] is True
        assert data["linked"] == 1  # match found…

        # …but no DB write made.
        await db.refresh(row)
        assert row.entity_id is None


class TestRelinkSelfAddressExclusion:
    @pytest.mark.asyncio
    async def test_self_address_in_participants_does_not_link_to_self_card(
        self, db: AsyncSession, admin_user: User
    ):
        """A row whose participant list contains a GmailConnection's primary
        or alias must not link to a contact card that owns that address —
        same pollution PR #202 fixed for the live sync path. The matcher
        sees only the third-party addresses, so the row stays unlinked
        when no other participant matches.
        """
        from src.email.models import InboundEmail
        from src.integrations.gmail.models import GmailConnection

        # Connection-owner's mailbox
        conn = GmailConnection(
            user_id=admin_user.id,
            email="accounting@linkcreativeco.com",
            aliases=["giancarlo@linkcreativeco.com"],
            access_token="t",
            refresh_token="t",
            token_expiry=None,
            scopes="",
        )
        db.add(conn)

        # A self-contact for the connection-owner exists (the pollution
        # case): if relink doesn't exclude self-addresses, it would link
        # the inbound row to THIS contact instead of leaving it unlinked.
        self_contact = Contact(
            email="accounting@linkcreativeco.com",
            first_name="Giancarlo",
            last_name="Self",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db.add(self_contact)
        await db.commit()
        await db.refresh(conn)
        await db.refresh(self_contact)

        # Inbound row: from a third party (no contact card for them) to
        # the connection's address. participant_emails is auto-populated
        # by the model listener.
        row = InboundEmail(
            resend_email_id="gmail:abc123",
            from_email="stranger@example.com",
            to_email="accounting@linkcreativeco.com",
            subject="hi",
            received_at=__import__("datetime").datetime(2026, 5, 1, tzinfo=__import__("datetime").timezone.utc),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        app = _make_app(db, admin_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/integrations/gmail/relink", json={})

        assert resp.status_code == 200
        await db.refresh(row)
        # Self-address excluded; no contact for stranger@; row stays NULL.
        assert row.entity_id is None
        assert row.entity_type is None

    @pytest.mark.asyncio
    async def test_self_address_excluded_but_third_party_still_links(
        self, db: AsyncSession, admin_user: User
    ):
        """Counterpart: the self-exclude must NOT mask a real contact
        match. An inbound CC'd to the connection's alias AND to a real
        contact should still link to the real contact.
        """
        from src.email.models import InboundEmail
        from src.integrations.gmail.models import GmailConnection

        conn = GmailConnection(
            user_id=admin_user.id,
            email="accounting@linkcreativeco.com",
            aliases=["giancarlo@linkcreativeco.com"],
            access_token="t",
            refresh_token="t",
            token_expiry=None,
            scopes="",
        )
        db.add(conn)

        target = Contact(
            email="customer@example.com",
            first_name="Real",
            last_name="Customer",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db.add(target)
        await db.commit()
        await db.refresh(target)

        row = InboundEmail(
            resend_email_id="gmail:def456",
            from_email="customer@example.com",
            to_email="accounting@linkcreativeco.com",
            cc="giancarlo@linkcreativeco.com",
            subject="thread",
            received_at=__import__("datetime").datetime(2026, 5, 1, tzinfo=__import__("datetime").timezone.utc),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        app = _make_app(db, admin_user)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/integrations/gmail/relink", json={})

        assert resp.status_code == 200
        await db.refresh(row)
        assert row.entity_type == "contacts"
        assert row.entity_id == target.id


# ---------------------------------------------------------------------------
# Helpers for rehydrate tests
# ---------------------------------------------------------------------------

# Minimal 1×1 PNG bytes (valid, decodable).
_TINY_PNG = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
    0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
    0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
    0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
    0x00, 0x00, 0x02, 0x00, 0x01, 0xE2, 0x21, 0xBC,
    0x33, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,
    0x44, 0xAE, 0x42, 0x60, 0x82,
])
_TINY_PNG_B64URL = base64.urlsafe_b64encode(_TINY_PNG).decode("ascii").rstrip("=")


def _make_gmail_message_with_unhydrated_attachment(msg_id: str, conn_email: str) -> dict:
    """Return a Gmail messages.get payload whose inline image part has only
    attachmentId set (no body.data) — simulating the pre-hydration state.

    The HTML body references the image via a cid: src.  After impl-worker's
    _hydrate_inline_attachments fetches the attachment data and _inline_cid_images
    runs, the src will become a data: URI.
    """
    html_b64 = base64.urlsafe_b64encode(
        b'<img src="cid:logo@example.com">'
    ).decode("ascii").rstrip("=")
    return {
        "id": msg_id,
        "threadId": "thread-1",
        "payload": {
            "mimeType": "multipart/related",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": conn_email},
                {"name": "Subject", "value": "Inline image test"},
                {"name": "Date", "value": "Wed, 01 May 2026 10:00:00 +0000"},
            ],
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": html_b64},
                },
                {
                    # Inline image part: has attachmentId but NO body.data.
                    # This is the shape Gmail returns for large-ish inline
                    # images — the data must be fetched separately via
                    # messages.attachments.get.
                    "mimeType": "image/png",
                    "filename": "logo.png",
                    "headers": [
                        {"name": "Content-ID", "value": "<logo@example.com>"},
                        {"name": "Content-Disposition", "value": "inline"},
                    ],
                    "body": {
                        "attachmentId": "att-1",
                        "size": len(_TINY_PNG),
                    },
                },
            ],
        },
    }


def _make_attachment_response() -> dict:
    """Return a Gmail messages.attachments.get payload for the inline PNG."""
    return {"data": _TINY_PNG_B64URL, "size": len(_TINY_PNG)}


def _make_rehydrate_http_client(msg_id: str) -> httpx.AsyncClient:
    """Build a MockTransport that handles both Gmail endpoints used by rehydrate:
      - GET .../users/me/messages/{msg_id}          → full message payload
      - GET .../users/me/messages/{msg_id}/attachments/att-1 → attachment data
    Longer (more specific) keys win so the attachment URL is matched before
    the message URL.
    """
    conn_email = "accounting@linkcreativeco.com"
    routes = {
        f"users/me/messages/{msg_id}/attachments/att-1": _make_attachment_response(),
        f"users/me/messages/{msg_id}": _make_gmail_message_with_unhydrated_attachment(
            msg_id, conn_email
        ),
    }
    sorted_routes = sorted(routes.items(), key=lambda kv: -len(kv[0]))

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for key, resp_body in sorted_routes:
            if key in url:
                return httpx.Response(200, json=resp_body)
        return httpx.Response(404, json={"error": "not found", "url": url})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _patch_gmail_client_http(http: httpx.AsyncClient):
    """Inject a pre-built httpx client into GmailClient.__init__."""
    from src.integrations.gmail.client import GmailClient as _GC

    orig_init = _GC.__init__

    def patched_init(self, conn, db_, http_arg=None):
        orig_init(self, conn, db_, http=http_arg or http)

    return patch.object(_GC, "__init__", patched_init)


# ---------------------------------------------------------------------------
# Tests: rehydrate-inline-images endpoint + attachment fetch
# ---------------------------------------------------------------------------


class TestRehydrateInlineImages:
    @pytest.mark.asyncio
    async def test_rehydrate_fetches_attachment_and_rewrites_cid(
        self, db: AsyncSession, admin_user: User
    ):
        """Full end-to-end: an InboundEmail row with a cid: reference in
        body_html is rehydrated when the Gmail message has an inline part
        that requires a separate attachments.get call to retrieve its data.

        The mock handles BOTH Gmail endpoints:
          - messages.get  → payload with image/png part (attachmentId only, no data)
          - messages.attachments.get → {"data": "<base64url PNG>"}

        After the endpoint runs, body_html must no longer contain "cid:" and
        must instead embed the image as a data:image/png;base64, URI.
        """
        from src.integrations.gmail.models import GmailConnection

        conn_email = "accounting@linkcreativeco.com"
        msg_id = "msg-rehydrate-1"

        conn = GmailConnection(
            user_id=admin_user.id,
            email=conn_email,
            aliases=[],
            access_token="fake-token",
            refresh_token="fake-refresh",
            # Set expiry far in the future so _refresh_if_needed is a no-op.
            token_expiry=datetime(2099, 1, 1, tzinfo=UTC),
            scopes="https://www.googleapis.com/auth/gmail.readonly",
        )
        db.add(conn)
        await db.commit()
        await db.refresh(conn)

        row = InboundEmail(
            resend_email_id=f"gmail:{msg_id}",
            from_email="sender@example.com",
            to_email=conn_email,
            subject="Inline image test",
            body_html='<img src="cid:logo@example.com">',
            received_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        assert "cid:" in (row.body_html or "")

        http = _make_rehydrate_http_client(msg_id)
        app = _make_app(db, admin_user)

        with _patch_gmail_client_http(http):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/integrations/gmail/rehydrate-inline-images", json={}
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["rehydrated"] >= 1
        # The row was rewritten — html_unchanged must be 0.
        assert data.get("skipped_breakdown", {}).get("html_unchanged", 0) == 0

        await db.refresh(row)
        assert "cid:" not in (row.body_html or ""), (
            "body_html still contains a cid: reference after rehydration"
        )
        assert "data:image/png;base64," in (row.body_html or ""), (
            "body_html does not contain the expected data: URI after rehydration"
        )

    @pytest.mark.asyncio
    async def test_rehydrate_dry_run_does_not_write(
        self, db: AsyncSession, admin_user: User
    ):
        """dry_run=True must not modify body_html even when the attachment
        fetch and cid substitution would succeed.
        """
        from src.integrations.gmail.models import GmailConnection

        conn_email = "accounting@linkcreativeco.com"
        msg_id = "msg-rehydrate-dry-2"

        conn = GmailConnection(
            user_id=admin_user.id,
            email=conn_email,
            aliases=[],
            access_token="fake-token",
            refresh_token="fake-refresh",
            token_expiry=datetime(2099, 1, 1, tzinfo=UTC),
            scopes="https://www.googleapis.com/auth/gmail.readonly",
        )
        db.add(conn)

        row = InboundEmail(
            resend_email_id=f"gmail:{msg_id}",
            from_email="sender@example.com",
            to_email=conn_email,
            subject="Dry run inline test",
            body_html='<img src="cid:logo@example.com">',
            received_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        original_html = row.body_html

        http = _make_rehydrate_http_client(msg_id)
        app = _make_app(db, admin_user)

        with _patch_gmail_client_http(http):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/integrations/gmail/rehydrate-inline-images",
                    json={"dry_run": True},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["dry_run"] is True
        # Match found and counted, but not written.
        assert data["rehydrated"] >= 1

        await db.refresh(row)
        assert row.body_html == original_html, (
            "body_html was modified during dry_run — no writes should occur"
        )

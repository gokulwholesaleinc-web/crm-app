"""Tests for the email search endpoint."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.email.models import EmailQueue, InboundEmail
from src.auth.utils import get_password_hash
from src.auth.jwt import create_access_token


async def _make_user(db: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash("pw"),
        full_name="User",
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_sent_email(
    db: AsyncSession,
    *,
    user_id: int,
    subject: str = "Hello",
    body: str = "body text",
    to_email: str = "dest@example.com",
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> EmailQueue:
    eq = EmailQueue(
        to_email=to_email,
        subject=subject,
        body=body,
        status="sent",
        attempts=1,
        sent_by_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(eq)
    await db.commit()
    await db.refresh(eq)
    return eq


async def _make_inbound_email(
    db: AsyncSession,
    *,
    to_email: str,
    from_email: str = "sender@example.com",
    subject: str = "Re: Hello",
    body_text: str = "reply text",
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> InboundEmail:
    from datetime import UTC, datetime

    ie = InboundEmail(
        resend_email_id=f"test-{subject[:10]}-{to_email}",
        from_email=from_email,
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        received_at=datetime.now(UTC),
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(ie)
    await db.commit()
    await db.refresh(ie)
    return ie


class TestEmailSearch:
    @pytest.mark.asyncio
    async def test_search_matches_sent_by_subject(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """A keyword in subject returns the sent email."""
        await _make_sent_email(
            db_session,
            user_id=test_user.id,
            subject="Quarterly Report",
            body="Please review the attached.",
        )
        resp = await client.get(
            "/api/email/search",
            params={"q": "Quarterly"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        kinds = {item["kind"] for item in data["items"]}
        assert "sent" in kinds

    @pytest.mark.asyncio
    async def test_search_matches_sent_by_body(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """A keyword in body returns the sent email."""
        await _make_sent_email(
            db_session,
            user_id=test_user.id,
            subject="Generic subject",
            body="The unique phrase xyzzy99 is here",
        )
        resp = await client.get(
            "/api/email/search",
            params={"q": "xyzzy99"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_search_no_match_returns_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """A query with no matching emails returns empty results."""
        resp = await client.get(
            "/api/email/search",
            params={"q": "zzz_no_match_ever_abcdef123"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_search_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Pagination returns correct slices."""
        for i in range(5):
            await _make_sent_email(
                db_session,
                user_id=test_user.id,
                subject=f"Paginationtest email {i}",
                body="common body",
                to_email=f"dest{i}@example.com",
            )
        resp_p1 = await client.get(
            "/api/email/search",
            params={"q": "Paginationtest", "page": 1, "page_size": 3},
            headers=auth_headers,
        )
        assert resp_p1.status_code == 200
        d1 = resp_p1.json()
        assert d1["total"] == 5
        assert len(d1["items"]) == 3
        assert d1["pages"] == 2

        resp_p2 = await client.get(
            "/api/email/search",
            params={"q": "Paginationtest", "page": 2, "page_size": 3},
            headers=auth_headers,
        )
        assert resp_p2.status_code == 200
        d2 = resp_p2.json()
        assert len(d2["items"]) == 2

    @pytest.mark.asyncio
    async def test_search_scoping_user_a_cannot_see_user_b_emails(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """User A's search must not return emails sent by user B."""
        user_b = await _make_user(db_session, "userb_scoping@example.com")
        await _make_sent_email(
            db_session,
            user_id=user_b.id,
            subject="ScopingTestSecretEmail",
            body="User B secret content",
        )
        resp = await client.get(
            "/api/email/search",
            params={"q": "ScopingTestSecretEmail"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_search_scoping_user_a_cannot_see_user_b_inbound(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Inbound emails are scoped to the user's connected Gmail address.
        User A (no Gmail OR a different Gmail) must not see InboundEmail
        rows whose to_email matches user B's Gmail address."""
        from src.integrations.gmail.models import GmailConnection
        user_b = await _make_user(db_session, "userb_inbound@example.com")
        userb_gmail = "userb_inbound_gmail@gmail.com"
        db_session.add(GmailConnection(
            user_id=user_b.id,
            email=userb_gmail,
            access_token="t",
            refresh_token="r",
            scopes="openid email profile gmail.send gmail.readonly",
        ))
        await _make_inbound_email(
            db_session,
            from_email="someone@external.com",
            to_email=userb_gmail,
            subject="InboundScopingProbeXYZ",
            body_text="User B inbound content",
        )
        await db_session.commit()
        resp = await client.get(
            "/api/email/search",
            params={"q": "InboundScopingProbeXYZ"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_search_entity_filter_narrows_results(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """entity_type + entity_id filter restricts results to that entity."""
        eq_linked = await _make_sent_email(
            db_session,
            user_id=test_user.id,
            subject="EntityFilterKeywordABC",
            body="body",
            entity_type="contacts",
            entity_id=999,
        )
        await _make_sent_email(
            db_session,
            user_id=test_user.id,
            subject="EntityFilterKeywordABC",
            body="body",
            entity_type="contacts",
            entity_id=888,
        )

        resp = await client.get(
            "/api/email/search",
            params={
                "q": "EntityFilterKeywordABC",
                "entity_type": "contacts",
                "entity_id": 999,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["entity_id"] == 999

    @pytest.mark.asyncio
    async def test_search_unauthenticated_returns_401(
        self,
        client: AsyncClient,
    ):
        """Unauthenticated request returns 401."""
        resp = await client.get("/api/email/search", params={"q": "test"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_search_snippet_contains_match(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Snippet field contains text around the match."""
        await _make_sent_email(
            db_session,
            user_id=test_user.id,
            subject="snippet test",
            body="A" * 100 + " uniqueSnippetWord " + "B" * 100,
        )
        resp = await client.get(
            "/api/email/search",
            params={"q": "uniqueSnippetWord"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        assert "uniqueSnippetWord" in items[0]["snippet"]

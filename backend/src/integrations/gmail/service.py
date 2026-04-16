"""GmailConnectionService — CRUD on GmailConnection + GmailSyncState."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.gmail.models import GmailConnection, GmailSyncState
from src.integrations.gmail import oauth as gmail_oauth


class GmailConnectionService:
    def __init__(self, db: AsyncSession, client_factory: gmail_oauth.HttpClientFactory = gmail_oauth.default_client_factory):
        self.db = db
        self._client_factory = client_factory

    async def get_by_user(self, user_id: int) -> Optional[GmailConnection]:
        result = await self.db.execute(
            select(GmailConnection).where(GmailConnection.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_sync_state(self, user_id: int) -> Optional[GmailSyncState]:
        result = await self.db.execute(
            select(GmailSyncState).where(GmailSyncState.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert_from_token_exchange(
        self,
        user_id: int,
        token_response: dict,
        email: str,
    ) -> GmailConnection:
        from datetime import timedelta

        existing = await self.get_by_user(user_id)

        expiry = None
        if "expires_in" in token_response:
            expiry = datetime.now(timezone.utc) + timedelta(seconds=token_response["expires_in"])

        if existing:
            existing.email = email
            existing.access_token = token_response["access_token"]
            if "refresh_token" in token_response:
                existing.refresh_token = token_response["refresh_token"]
            existing.token_expiry = expiry
            existing.scopes = gmail_oauth.CANONICAL_SCOPES
            existing.revoked_at = None
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            conn = existing
        else:
            conn = GmailConnection(
                user_id=user_id,
                email=email,
                access_token=token_response["access_token"],
                refresh_token=token_response.get("refresh_token"),
                token_expiry=expiry,
                scopes=gmail_oauth.CANONICAL_SCOPES,
            )
            self.db.add(conn)
            await self.db.flush()

        # Upsert GmailSyncState with last_history_id=None (first sync seeds it)
        sync_state = await self.get_sync_state(user_id)
        if not sync_state:
            sync_state = GmailSyncState(user_id=user_id, last_history_id=None)
            self.db.add(sync_state)
            await self.db.flush()

        return conn

    async def mark_revoked(self, user_id: int) -> Optional[GmailConnection]:
        conn = await self.get_by_user(user_id)
        if not conn:
            return None
        # Revoke via Google
        token = conn.refresh_token or conn.access_token
        if token:
            await gmail_oauth.revoke_token(token, self._client_factory)
        conn.revoked_at = datetime.now(timezone.utc)
        conn.access_token = ""
        conn.refresh_token = None
        conn.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return conn

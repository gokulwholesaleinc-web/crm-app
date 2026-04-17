"""Gmail connection service."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.integrations.gmail import oauth as gmail_oauth
from src.integrations.gmail.models import GmailConnection, GmailSyncState


class GmailConnectionService:
    def __init__(self, db: AsyncSession, client_factory: gmail_oauth.HttpClientFactory = gmail_oauth.default_client_factory):
        self.db = db
        self._client_factory = client_factory

    async def get_by_user(self, user_id: int) -> GmailConnection | None:
        result = await self.db.execute(
            select(GmailConnection).where(GmailConnection.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_sync_state(self, user_id: int) -> GmailSyncState | None:
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
            expiry = datetime.now(UTC) + timedelta(seconds=token_response["expires_in"])

        if existing:
            existing.email = email
            existing.access_token = token_response["access_token"]
            if "refresh_token" in token_response:
                existing.refresh_token = token_response["refresh_token"]
            existing.token_expiry = expiry
            existing.scopes = gmail_oauth.CANONICAL_SCOPES
            existing.revoked_at = None
            existing.updated_at = datetime.now(UTC)
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

    async def seed_sync_cursor(self, connection: GmailConnection) -> None:
        """Seed last_history_id with the account's current historyId.

        Called right after a successful connect so the first background sync
        pulls every message that arrives *after* the connect moment. Without
        this seed, the first sync tick would just learn the cursor and return
        empty — dropping any reply that lands in the gap.

        Update-only: upsert_from_token_exchange guarantees the sync_state row
        exists before we're called, which keeps us off the check-then-insert
        race with the scheduler's own create path.
        """
        from src.integrations.gmail.client import GmailClient

        sync_state = await self.get_sync_state(connection.user_id)
        if sync_state is None:
            return

        async with GmailClient(connection, self.db) as client:
            profile = await client.get_profile()

        sync_state.last_history_id = str(profile["historyId"])
        sync_state.last_synced_at = datetime.now(UTC)
        sync_state.failure_count = 0
        sync_state.last_error = None
        await self.db.flush()

    async def mark_revoked(self, user_id: int) -> GmailConnection | None:
        conn = await self.get_by_user(user_id)
        if not conn:
            return None
        # Revoke via Google
        token = conn.refresh_token or conn.access_token
        if token:
            await gmail_oauth.revoke_token(token, self._client_factory)
        conn.revoked_at = datetime.now(UTC)
        conn.access_token = ""
        conn.refresh_token = None
        conn.updated_at = datetime.now(UTC)
        await self.db.flush()
        return conn

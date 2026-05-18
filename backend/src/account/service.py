"""Service layer for account-settings persistence.

Each user has at most one row per table; both rows are lazy-created on
first access. ``event_matrix`` updates are deep-merged so flipping a
single event toggle doesn't wipe peer keys.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.account.models import UserNotificationPrefs, UserPreferences
from src.account.schemas import (
    AccountPreferencesUpdate,
    NotificationPrefsUpdate,
)


class AccountPrefsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_notification_prefs(
        self, user_id: int
    ) -> UserNotificationPrefs:
        result = await self.db.execute(
            select(UserNotificationPrefs).where(
                UserNotificationPrefs.user_id == user_id
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row
        row = UserNotificationPrefs(user_id=user_id, event_matrix={})
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def update_notification_prefs(
        self, user_id: int, data: NotificationPrefsUpdate
    ) -> UserNotificationPrefs:
        row = await self.get_or_create_notification_prefs(user_id)
        payload = data.model_dump(exclude_unset=True)

        new_matrix = payload.pop("event_matrix", None)
        if new_matrix is not None:
            merged = dict(row.event_matrix or {})
            for event_type, channels in new_matrix.items():
                base = dict(merged.get(event_type) or {})
                base.update(channels)
                merged[event_type] = base
            row.event_matrix = merged

        for field, value in payload.items():
            setattr(row, field, value)

        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def get_or_create_preferences(self, user_id: int) -> UserPreferences:
        result = await self.db.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row
        row = UserPreferences(user_id=user_id)
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def update_preferences(
        self, user_id: int, data: AccountPreferencesUpdate
    ) -> UserPreferences:
        row = await self.get_or_create_preferences(user_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            next_value = value
            if field == "guide_progress":
                next_value = value or {}
            setattr(row, field, next_value)
        await self.db.flush()
        await self.db.refresh(row)
        return row

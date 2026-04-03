"""Email throttle service - daily send limits and warmup management."""

import math
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.email.models import EmailQueue, EmailSettings


class EmailThrottleService:
    """Manages daily email send limits and warmup schedule."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_settings(self) -> EmailSettings:
        """Get or create the singleton email settings row."""
        result = await self.db.execute(select(EmailSettings).limit(1))
        settings = result.scalar_one_or_none()
        if not settings:
            settings = EmailSettings()
            self.db.add(settings)
            await self.db.flush()
            await self.db.refresh(settings)
        return settings

    async def get_today_sent_count(self) -> int:
        """Count emails with status='sent' and sent_at = today (UTC)."""
        today = date.today()
        result = await self.db.execute(
            select(func.count(EmailQueue.id)).where(
                EmailQueue.status == "sent",
                func.date(EmailQueue.sent_at) == today,
            )
        )
        return result.scalar() or 0

    # Fixed warmup tiers: (max_day, emails_per_day)
    _WARMUP_TIERS = [(3, 20), (6, 40), (9, 60)]

    async def get_effective_daily_limit(self) -> int:
        """Return the current effective daily send limit.

        If warmup is enabled and warmup_start_date is set:
          Day 1-3: 20/day, Day 4-6: 40/day, Day 7-9: 60/day,
          then +20% daily until warmup_target_daily is reached.
        Otherwise, return the configured daily_send_limit.
        """
        settings = await self.get_settings()
        if not settings.warmup_enabled or not settings.warmup_start_date:
            return settings.daily_send_limit

        days_elapsed = (date.today() - settings.warmup_start_date).days + 1
        if days_elapsed < 1:
            return settings.daily_send_limit

        # Check fixed tiers first
        limit = None
        for max_day, tier_limit in self._WARMUP_TIERS:
            if days_elapsed <= max_day:
                limit = tier_limit
                break

        # After day 9, start at 60 and increase by 20% each day
        if limit is None:
            extra_days = days_elapsed - 9
            limit = math.floor(60 * (1.2 ** extra_days))

        return min(limit, settings.warmup_target_daily)

    async def can_send(self) -> bool:
        """Return True if we haven't hit the daily send limit yet."""
        sent = await self.get_today_sent_count()
        limit = await self.get_effective_daily_limit()
        return sent < limit

    async def get_volume_stats(self) -> dict:
        """Return current email volume statistics."""
        settings = await self.get_settings()
        sent_today = await self.get_today_sent_count()
        daily_limit = await self.get_effective_daily_limit()

        warmup_day = None
        if settings.warmup_enabled and settings.warmup_start_date:
            warmup_day = (date.today() - settings.warmup_start_date).days + 1

        return {
            "sent_today": sent_today,
            "daily_limit": settings.daily_send_limit,
            "warmup_enabled": settings.warmup_enabled,
            "warmup_day": warmup_day,
            "warmup_current_limit": daily_limit if settings.warmup_enabled else None,
            "remaining_today": max(0, daily_limit - sent_today),
        }

    async def update_settings(
        self,
        daily_send_limit: int | None = None,
        warmup_enabled: bool | None = None,
        warmup_start_date: date | None = None,
        warmup_target_daily: int | None = None,
    ) -> EmailSettings:
        """Update email settings."""
        settings = await self.get_settings()
        if daily_send_limit is not None:
            settings.daily_send_limit = daily_send_limit
        if warmup_enabled is not None:
            settings.warmup_enabled = warmup_enabled
        if warmup_start_date is not None:
            settings.warmup_start_date = warmup_start_date
        if warmup_target_daily is not None:
            settings.warmup_target_daily = warmup_target_daily
        await self.db.flush()
        await self.db.refresh(settings)
        return settings

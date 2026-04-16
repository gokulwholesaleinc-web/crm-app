"""Gmail sync scheduler hook.

The project uses a consolidated APScheduler tick in backend/src/core/scheduler.py.
Call schedule_gmail_sync(scheduler) from there (or from start_scheduler) to register
the gmail sync job at the same 90-second cadence.

If you prefer to wire it inline, just add:
    await _sync_gmail_accounts()
inside _background_tick in core/scheduler.py.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


async def _sync_gmail_accounts() -> None:
    from src.integrations.gmail.sync import GmailSyncWorker
    try:
        await GmailSyncWorker.sync_all_active()
    except Exception as exc:
        logger.error("[gmail_sync] tick error: %s", exc)


def schedule_gmail_sync(scheduler: AsyncIOScheduler) -> None:
    """Add the gmail_sync job to an existing APScheduler instance."""
    scheduler.add_job(
        _sync_gmail_accounts,
        trigger=IntervalTrigger(seconds=90),
        id="gmail_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info("Gmail sync job registered (every 90s)")

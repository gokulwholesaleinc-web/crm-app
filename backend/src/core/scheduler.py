"""Background task scheduler using APScheduler."""

import logging
from typing import Callable, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import src.database as db_module

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_scheduled_job(job_name: str, service_factory: Callable, method: str) -> Any:
    """Run a scheduled job with session management, commit, and logging."""
    try:
        async with db_module.async_session_maker() as session:
            service = service_factory(session)
            result = await getattr(service, method)()
            await session.commit()
            if result:
                logger.info("[%s] Processed %s item(s)", job_name, result if isinstance(result, int) else len(result))
            return result
    except Exception as e:
        logger.error("[%s] Error: %s", job_name, e)


async def _process_due_sequence_steps():
    from src.sequences.service import SequenceService
    await _run_scheduled_job("sequence_steps", SequenceService, "process_due_steps")


async def _process_email_retries():
    from src.email.service import EmailService
    await _run_scheduled_job("email_retries", EmailService, "process_retries")


async def _process_due_campaign_steps():
    from src.campaigns.service import CampaignService
    await _run_scheduled_job("campaign_steps", CampaignService, "process_due_campaign_steps")


async def _deliver_scheduled_reports():
    from src.reports.delivery import ReportDeliveryService
    await _run_scheduled_job("report_delivery", ReportDeliveryService, "deliver_due_reports")


async def _sync_google_calendars():
    from sqlalchemy import select
    from src.integrations.google_calendar.models import GoogleCalendarCredential
    from src.integrations.google_calendar.service import GoogleCalendarService

    async with db_module.async_session_maker() as session:
        result = await session.execute(select(GoogleCalendarCredential))
        credentials = result.scalars().all()

    for credential in credentials:
        try:
            async with db_module.async_session_maker() as session:
                service = GoogleCalendarService(session)
                synced = await service.sync_from_google(credential.user_id)
                await session.commit()
                if synced:
                    logger.info("[google_calendar_sync] user_id=%s synced %s event(s)", credential.user_id, len(synced))
        except Exception as e:
            logger.error("[google_calendar_sync] user_id=%s error: %s", credential.user_id, e)


async def _background_tick():
    # Single periodic wakeup runs all five handlers sequentially so Neon's
    # compute only has to come out of autosuspend once per interval.
    await _process_email_retries()
    await _process_due_sequence_steps()
    await _process_due_campaign_steps()
    await _deliver_scheduled_reports()
    await _sync_google_calendars()
    await _sync_gmail_accounts()


def start_scheduler():
    """Register the consolidated background tick and start the scheduler."""
    scheduler.add_job(
        _background_tick,
        trigger=IntervalTrigger(minutes=90),
        id="background_tick",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info("Background scheduler started (consolidated tick every 90m)")


def stop_scheduler():
    """Shut down the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")


async def _sync_gmail_accounts():
    from src.integrations.gmail.scheduler import _sync_gmail_accounts as _gmail_sync
    await _gmail_sync()

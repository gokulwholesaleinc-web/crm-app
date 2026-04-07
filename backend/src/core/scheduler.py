"""Background task scheduler using APScheduler."""

import logging
from typing import Callable, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.database import async_session_maker

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _run_scheduled_job(job_name: str, service_factory: Callable, method: str) -> Any:
    """Run a scheduled job with session management, commit, and logging."""
    try:
        async with async_session_maker() as session:
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


def start_scheduler():
    """Register jobs and start the scheduler."""
    scheduler.add_job(
        _process_due_sequence_steps,
        trigger=IntervalTrigger(minutes=15),
        id="process_due_sequence_steps",
        replace_existing=True,
    )
    scheduler.add_job(
        _process_email_retries,
        trigger=IntervalTrigger(minutes=10),
        id="process_email_retries",
        replace_existing=True,
    )
    scheduler.add_job(
        _process_due_campaign_steps,
        trigger=IntervalTrigger(minutes=15),
        id="process_due_campaign_steps",
        replace_existing=True,
    )
    scheduler.add_job(
        _deliver_scheduled_reports,
        trigger=IntervalTrigger(minutes=30),
        id="deliver_scheduled_reports",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Background scheduler started with 4 jobs")


def stop_scheduler():
    """Shut down the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")

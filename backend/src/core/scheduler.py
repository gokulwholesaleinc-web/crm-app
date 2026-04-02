"""Background task scheduler using APScheduler."""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.database import async_session_maker

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _process_due_sequence_steps():
    """Process sequence enrollments that have steps due."""
    from src.sequences.service import SequenceService

    try:
        async with async_session_maker() as session:
            service = SequenceService(session)
            results = await service.process_due_steps()
            await session.commit()
            if results:
                logger.info("Processed %d due sequence steps", len(results))
    except Exception as e:
        logger.error("Error processing due sequence steps: %s", e)


async def _process_email_retries():
    """Retry failed emails with exponential backoff."""
    from src.email.service import EmailService

    try:
        async with async_session_maker() as session:
            service = EmailService(session)
            retried = await service.process_retries()
            await session.commit()
            if retried:
                logger.info("Retried %d failed emails", retried)
    except Exception as e:
        logger.error("Error processing email retries: %s", e)


def start_scheduler():
    """Register jobs and start the scheduler."""
    scheduler.add_job(
        _process_due_sequence_steps,
        trigger=IntervalTrigger(minutes=5),
        id="process_due_sequence_steps",
        replace_existing=True,
    )
    scheduler.add_job(
        _process_email_retries,
        trigger=IntervalTrigger(minutes=2),
        id="process_email_retries",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Background scheduler started")


def stop_scheduler():
    """Shut down the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")

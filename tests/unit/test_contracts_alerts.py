"""Tests for the daily contract lifecycle scheduler job.

Covers: signed→active auto-flip and expiring-soon alert dedup logic.
No mocks — all assertions hit the in-memory SQLite test DB.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.models import Contract
from src.contracts.scheduler import ContractLifecycleService
from src.email.models import EmailQueue
from src.notifications.models import Notification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_contract(db_session, user, **kwargs) -> Contract:
    contract = Contract(
        title=kwargs.pop("title", "Test Contract"),
        status=kwargs.pop("status", "draft"),
        owner_id=user.id,
        created_by_id=user.id,
        **kwargs,
    )
    db_session.add(contract)
    return contract


# ---------------------------------------------------------------------------
# Auto-flip: signed → active
# ---------------------------------------------------------------------------

class TestSignedToActiveFlip:

    async def test_flip_signed_past_start_date(
        self, db_session: AsyncSession, test_user
    ):
        """Contract status=signed with start_date=yesterday flips to active."""
        contract = _make_contract(
            db_session,
            test_user,
            status="signed",
            start_date=date.today() - timedelta(days=1),
        )
        await db_session.commit()

        svc = ContractLifecycleService(db_session)
        total = await svc.process_due_contracts()
        await db_session.commit()

        await db_session.refresh(contract)
        assert contract.status == "active"
        assert total >= 1

    async def test_flip_skips_future_start_date(
        self, db_session: AsyncSession, test_user
    ):
        """Contract status=signed with start_date=tomorrow stays signed."""
        contract = _make_contract(
            db_session,
            test_user,
            status="signed",
            start_date=date.today() + timedelta(days=1),
        )
        await db_session.commit()

        svc = ContractLifecycleService(db_session)
        await svc.process_due_contracts()
        await db_session.commit()

        await db_session.refresh(contract)
        assert contract.status == "signed"

    async def test_flip_skips_null_start_date(
        self, db_session: AsyncSession, test_user
    ):
        """Contract status=signed with no start_date is not flipped."""
        contract = _make_contract(
            db_session,
            test_user,
            status="signed",
            start_date=None,
        )
        await db_session.commit()

        svc = ContractLifecycleService(db_session)
        await svc.process_due_contracts()
        await db_session.commit()

        await db_session.refresh(contract)
        assert contract.status == "signed"


# ---------------------------------------------------------------------------
# Expiring-soon alert
# ---------------------------------------------------------------------------

class TestExpiringAlert:

    async def test_alert_fires_for_expiring_contract(
        self, db_session: AsyncSession, test_user
    ):
        """Active contract expiring in 10 days creates Notification + EmailQueue row."""
        test_user.email = "owner@example.com"
        await db_session.flush()

        contract = _make_contract(
            db_session,
            test_user,
            status="active",
            end_date=date.today() + timedelta(days=10),
            expiring_notified_at=None,
        )
        await db_session.commit()

        svc = ContractLifecycleService(db_session)
        total = await svc.process_due_contracts()
        await db_session.commit()

        assert total >= 1
        assert contract.expiring_notified_at is not None

        from sqlalchemy import select
        notif_result = await db_session.execute(
            select(Notification).where(
                Notification.entity_type == "contracts",
                Notification.entity_id == contract.id,
                Notification.user_id == test_user.id,
            )
        )
        notif = notif_result.scalar_one_or_none()
        assert notif is not None
        assert "expiring" in notif.title.lower()

        email_result = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == "contracts",
                EmailQueue.entity_id == contract.id,
            )
        )
        email_row = email_result.scalar_one_or_none()
        assert email_row is not None
        assert email_row.to_email == test_user.email

    async def test_alert_deduplicates_within_window(
        self, db_session: AsyncSession, test_user
    ):
        """Running the job twice within the window does not create a second notification."""
        test_user.email = "owner2@example.com"
        await db_session.flush()

        contract = _make_contract(
            db_session,
            test_user,
            status="active",
            end_date=date.today() + timedelta(days=10),
            expiring_notified_at=None,
        )
        await db_session.commit()

        svc = ContractLifecycleService(db_session)
        await svc.process_due_contracts()
        await db_session.commit()

        # Second run — should be suppressed
        await svc.process_due_contracts()
        await db_session.commit()

        from sqlalchemy import func, select
        count_result = await db_session.execute(
            select(func.count()).where(
                Notification.entity_type == "contracts",
                Notification.entity_id == contract.id,
            )
        )
        assert count_result.scalar() == 1

    async def test_alert_refires_after_30d(
        self, db_session: AsyncSession, test_user
    ):
        """Alert re-fires when expiring_notified_at is more than 30 days ago."""
        test_user.email = "owner3@example.com"
        await db_session.flush()

        old_notify = datetime.now(UTC) - timedelta(days=31)
        contract = _make_contract(
            db_session,
            test_user,
            status="active",
            end_date=date.today() + timedelta(days=10),
            expiring_notified_at=old_notify,
        )
        await db_session.commit()

        svc = ContractLifecycleService(db_session)
        total = await svc.process_due_contracts()
        await db_session.commit()

        assert total >= 1
        await db_session.refresh(contract)
        assert contract.expiring_notified_at is not None
        # SQLite returns tz-naive datetimes; strip tz for comparison
        notified = contract.expiring_notified_at
        if notified.tzinfo is None:
            old_naive = old_notify.replace(tzinfo=None)
        else:
            old_naive = old_notify
        assert notified > old_naive

    async def test_alert_skips_far_future_end_date(
        self, db_session: AsyncSession, test_user
    ):
        """Active contract expiring in 90 days is NOT notified."""
        contract = _make_contract(
            db_session,
            test_user,
            status="active",
            end_date=date.today() + timedelta(days=90),
            expiring_notified_at=None,
        )
        await db_session.commit()

        svc = ContractLifecycleService(db_session)
        await svc.process_due_contracts()
        await db_session.commit()

        await db_session.refresh(contract)
        assert contract.expiring_notified_at is None

    async def test_alert_skips_already_past_end_date(
        self, db_session: AsyncSession, test_user
    ):
        """Active contract with end_date in the past is not processed by this job."""
        contract = _make_contract(
            db_session,
            test_user,
            status="active",
            end_date=date.today() - timedelta(days=1),
            expiring_notified_at=None,
        )
        await db_session.commit()

        svc = ContractLifecycleService(db_session)
        await svc.process_due_contracts()
        await db_session.commit()

        await db_session.refresh(contract)
        assert contract.expiring_notified_at is None

    async def test_alert_skips_contract_without_owner(
        self, db_session: AsyncSession, test_user
    ):
        """Contract with owner_id=None is skipped silently without crashing."""
        contract = Contract(
            title="Ownerless Contract",
            status="active",
            end_date=date.today() + timedelta(days=10),
            owner_id=None,
            created_by_id=test_user.id,
            expiring_notified_at=None,
        )
        db_session.add(contract)
        await db_session.commit()

        svc = ContractLifecycleService(db_session)
        # Should not raise
        await svc.process_due_contracts()
        await db_session.commit()

        # expiring_notified_at still set (loop ran) but no notification/email created
        await db_session.refresh(contract)
        # The contract matched the query (active, end_date in window, not notified),
        # so expiring_notified_at is set to now — but _notify_owner returns early.
        assert contract.expiring_notified_at is not None

        from sqlalchemy import select
        notif_count = await db_session.execute(
            select(Notification).where(
                Notification.entity_type == "contracts",
                Notification.entity_id == contract.id,
            )
        )
        assert notif_count.scalar_one_or_none() is None

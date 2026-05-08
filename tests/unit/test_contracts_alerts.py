"""Tests for the daily contract lifecycle scheduler job.

Covers: signed→active auto-flip and expiring-soon alert dedup logic.
No mocks — all assertions hit the in-memory SQLite test DB.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.account.models import UserNotificationPrefs
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

        # Opt test_user in — required under the opt-in gate.
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            in_app_enabled=True,
            email_enabled=True,
            event_matrix={"contract_expiring": {"in_app": True, "email": True}},
        )
        db_session.add(prefs)
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
        """Contract with owner_id=None is skipped silently without crashing.

        After the channel-aware cooldown refactor, an ownerless contract
        leaves BOTH cooldown columns NULL (we no longer prematurely
        stamp before knowing whether the channel actually fires). This
        is intentional: if an owner is later assigned, the next scan
        re-considers it.
        """
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

        await db_session.refresh(contract)
        assert contract.expiring_notified_at is None
        assert contract.expiring_email_notified_at is None

        from sqlalchemy import select
        notif_count = await db_session.execute(
            select(Notification).where(
                Notification.entity_type == "contracts",
                Notification.entity_id == contract.id,
            )
        )
        assert notif_count.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Channel-aware cooldown (PR A — migration 028)
# ---------------------------------------------------------------------------

class TestChannelAwareCooldown:
    """Each channel keeps its own cooldown stamp.

    Before this PR, a single ``expiring_notified_at`` stamped
    unconditionally after in-app fired, blocking BOTH channels even when
    email had been gated off — a user who flipped email back on was
    silently locked out for up to ``EXPIRING_WINDOW_DAYS``.
    """

    async def test_email_off_does_not_consume_email_cooldown(
        self, db_session: AsyncSession, test_user
    ):
        """Email pref off → in-app stamp set, email stamp stays NULL."""
        from src.account.models import UserNotificationPrefs

        test_user.email = "owner-cooldown@example.com"
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            event_matrix={"contract_expiring": {"email": False}},
        )
        db_session.add(prefs)
        await db_session.flush()

        contract = _make_contract(
            db_session,
            test_user,
            status="active",
            end_date=date.today() + timedelta(days=10),
            expiring_notified_at=None,
            expiring_email_notified_at=None,
        )
        await db_session.commit()

        await ContractLifecycleService(db_session).process_due_contracts()
        await db_session.commit()

        await db_session.refresh(contract)
        assert contract.expiring_notified_at is not None
        assert contract.expiring_email_notified_at is None

        from sqlalchemy import select
        email_q = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == "contracts",
                EmailQueue.entity_id == contract.id,
            )
        )
        assert email_q.scalar_one_or_none() is None

    async def test_email_pref_flip_on_fires_email_next_scan(
        self, db_session: AsyncSession, test_user
    ):
        """Re-enabling email after a previous in-app-only fire delivers the email."""
        from src.account.models import UserNotificationPrefs

        test_user.email = "owner-flip@example.com"
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            event_matrix={"contract_expiring": {"email": False}},
        )
        db_session.add(prefs)
        await db_session.flush()

        contract = _make_contract(
            db_session,
            test_user,
            status="active",
            end_date=date.today() + timedelta(days=10),
            expiring_notified_at=None,
            expiring_email_notified_at=None,
        )
        await db_session.commit()

        # First scan with email off — only in_app fires.
        await ContractLifecycleService(db_session).process_due_contracts()
        await db_session.commit()

        await db_session.refresh(contract)
        assert contract.expiring_notified_at is not None
        assert contract.expiring_email_notified_at is None

        # User re-enables email for contract_expiring.
        prefs.event_matrix = {"contract_expiring": {"email": True}}
        await db_session.flush()
        # JSON column isn't wrapped in MutableDict on this model, so a
        # whole-value rebind is enough in practice — flag_modified is
        # belt-and-suspenders to make the dirty signal explicit. Don't
        # cargo-cult onto plain assignments elsewhere.
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(prefs, "event_matrix")
        await db_session.commit()

        # Second scan — in_app cooldown is still hot (just stamped),
        # email cooldown is NULL → only email fires now.
        await ContractLifecycleService(db_session).process_due_contracts()
        await db_session.commit()

        await db_session.refresh(contract)
        assert contract.expiring_email_notified_at is not None

        from sqlalchemy import select
        email_q = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == "contracts",
                EmailQueue.entity_id == contract.id,
            )
        )
        rows = list(email_q.scalars().all())
        assert len(rows) == 1
        assert rows[0].to_email == test_user.email

        # In-app stayed deduped — only the original notification exists.
        from sqlalchemy import func
        notif_count = await db_session.execute(
            select(func.count()).where(
                Notification.entity_type == "contracts",
                Notification.entity_id == contract.id,
            )
        )
        assert notif_count.scalar() == 1

    async def test_both_channels_stamp_on_full_fire(
        self, db_session: AsyncSession, test_user
    ):
        """Default prefs (both channels allowed) → both columns stamped."""
        test_user.email = "owner-both@example.com"
        await db_session.flush()

        contract = _make_contract(
            db_session,
            test_user,
            status="active",
            end_date=date.today() + timedelta(days=10),
            expiring_notified_at=None,
            expiring_email_notified_at=None,
        )
        await db_session.commit()

        await ContractLifecycleService(db_session).process_due_contracts()
        await db_session.commit()

        await db_session.refresh(contract)
        assert contract.expiring_notified_at is not None
        assert contract.expiring_email_notified_at is not None

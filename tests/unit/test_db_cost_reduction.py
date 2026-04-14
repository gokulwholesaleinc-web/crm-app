"""
Tests for the DB cost-reduction backend fixes.

Covers:
1. Kanban N+1: PipelineManager.get_kanban_data preserves the existing
   shape and eager-loads contact.full_name and company.name.
2. Router dashboard cache TTL: bumped to 3 minutes so repeat dashboard
   loads don't thrash Neon.
3. Scheduler consolidation: start_scheduler registers a single 15-minute
   tick that runs all four handlers so Neon's compute only wakes once per
   interval (4 wakeups/hr) instead of once per staggered job (8+/hr).
"""

import pytest
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.companies.models import Company
from src.contacts.models import Contact
from src.opportunities.models import Opportunity, PipelineStage
from src.opportunities.pipeline import PipelineManager


# =============================================================================
# Fix 3 — Kanban N+1
# =============================================================================


class TestKanbanEagerLoad:
    """PipelineManager.get_kanban_data should eager-load contact + company."""

    @pytest.mark.asyncio
    async def test_get_kanban_data_returns_expected_shape(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_pipeline_stage: PipelineStage,
        test_contact: Contact,
        test_company: Company,
    ):
        """Kanban data exposes stage metadata and the opportunity list."""
        opportunity = Opportunity(
            name="Eager Load Deal",
            pipeline_stage_id=test_pipeline_stage.id,
            amount=10000.0,
            currency="USD",
            expected_close_date=date.today() + timedelta(days=14),
            contact_id=test_contact.id,
            company_id=test_company.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(opportunity)
        await db_session.commit()

        manager = PipelineManager(db_session)
        kanban = await manager.get_kanban_data(owner_id=test_user.id)

        # Locate the stage we seeded an opportunity into.
        stage_data = next(
            (s for s in kanban if s["stage_id"] == test_pipeline_stage.id),
            None,
        )
        assert stage_data is not None
        for field in (
            "stage_id",
            "stage_name",
            "color",
            "probability",
            "is_won",
            "is_lost",
            "opportunities",
            "total_amount",
            "total_weighted",
            "count",
        ):
            assert field in stage_data, f"missing field: {field}"

        assert stage_data["count"] == 1
        assert stage_data["total_amount"] == 10000.0

        opp_payload = stage_data["opportunities"][0]
        # Eager-loaded contact + company should resolve to full_name and
        # company name without an extra lazy-load round-trip.
        assert opp_payload["contact_name"] == "John Doe"
        assert opp_payload["company_name"] == "Test Company Inc"
        assert opp_payload["owner_id"] == test_user.id

    @pytest.mark.asyncio
    async def test_get_kanban_data_filters_by_owner(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_pipeline_stage: PipelineStage,
    ):
        """Owner filter excludes opportunities owned by other users."""
        other_owner = User(
            email="other_owner@example.com",
            hashed_password="x",
            full_name="Other Owner",
            is_active=True,
        )
        db_session.add(other_owner)
        await db_session.commit()
        await db_session.refresh(other_owner)

        mine = Opportunity(
            name="Mine",
            pipeline_stage_id=test_pipeline_stage.id,
            amount=1.0,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        theirs = Opportunity(
            name="Theirs",
            pipeline_stage_id=test_pipeline_stage.id,
            amount=2.0,
            owner_id=other_owner.id,
            created_by_id=other_owner.id,
        )
        db_session.add_all([mine, theirs])
        await db_session.commit()

        manager = PipelineManager(db_session)
        kanban = await manager.get_kanban_data(owner_id=test_user.id)

        names = [
            opp["name"]
            for stage in kanban
            for opp in stage["opportunities"]
        ]
        assert "Mine" in names
        assert "Theirs" not in names


# =============================================================================
# Router dashboard cache — TTL bumped so Neon can auto-suspend
# =============================================================================


class TestDashboardCacheTTL:
    """The dashboard result cache TTL should be 3 minutes (180s)."""

    def test_dashboard_cache_ttl_is_three_minutes(self):
        from src.dashboard.router import _DASHBOARD_CACHE_TTL

        assert _DASHBOARD_CACHE_TTL == 180


# =============================================================================
# Fix 1 — Scheduler intervals
# =============================================================================


class TestSchedulerConsolidation:
    """start_scheduler should register a single consolidated tick so Neon's
    compute only wakes once per interval."""

    def test_scheduler_uses_single_consolidated_tick(self):
        """Only one job ('background_tick') is registered, every 15 minutes."""
        from src.core.scheduler import scheduler, start_scheduler, stop_scheduler

        was_running = scheduler.running
        if not was_running:
            start_scheduler()
        try:
            jobs = scheduler.get_jobs()
            assert len(jobs) == 1, (
                f"expected 1 consolidated job, got {len(jobs)}: "
                f"{[j.id for j in jobs]}"
            )

            tick = scheduler.get_job("background_tick")
            assert tick is not None, "background_tick job not registered"
            assert tick.trigger.interval.total_seconds() == 15 * 60
            assert tick.coalesce is True
            assert tick.max_instances == 1
        finally:
            if not was_running:
                stop_scheduler()

    def test_background_tick_is_async_callable(self):
        """_background_tick exists and is an async coroutine function."""
        import inspect
        from src.core.scheduler import _background_tick

        assert inspect.iscoroutinefunction(_background_tick)

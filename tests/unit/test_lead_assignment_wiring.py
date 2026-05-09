"""Wiring tests: LeadService.create routes through AssignmentService.

Pins the contract between the lead-create code path and the assignment
rule engine: a lead arriving without an explicit `owner_id` must be
auto-routed (when a rule matches) and the choice must be audited; a
lead arriving with an explicit `owner_id` must be honored verbatim and
skip both routing and audit.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.assignment.models import AssignmentLog, AssignmentRule
from src.auth.models import User
from src.auth.security import get_password_hash
from src.leads.schemas import LeadCreate
from src.leads.service import LeadService


@pytest_asyncio.fixture
async def second_user(db_session: AsyncSession) -> User:
    user = User(
        email="second-wiring@example.com",
        hashed_password=get_password_hash("pw"),
        full_name="Second Wiring",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _add_rule(
    db: AsyncSession,
    *,
    name: str,
    user_ids: list[int],
    filters: dict | None = None,
    is_default: bool = False,
    is_active: bool = True,
    created_by: int,
) -> AssignmentRule:
    rule = AssignmentRule(
        name=name,
        assignment_type="round_robin",
        user_ids=user_ids,
        filters=filters,
        last_assigned_index=-1,
        is_active=is_active,
        is_default=is_default,
        created_by_id=created_by,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


class TestLeadCreateAutoAssign:
    @pytest.mark.asyncio
    async def test_create_without_owner_routes_via_rule_and_logs(
        self,
        db_session: AsyncSession,
        test_user: User,
        second_user: User,
    ):
        """No owner + active rule → owner picked + assignment_log row written."""
        await _add_rule(
            db_session,
            name="all-leads RR",
            user_ids=[test_user.id, second_user.id],
            created_by=test_user.id,
        )

        service = LeadService(db_session)
        lead = await service.create(
            LeadCreate(first_name="Auto", last_name="Routed", status="new"),
            user_id=test_user.id,
        )

        assert lead.owner_id == test_user.id  # round-robin index -1 → 0
        rows = (await db_session.execute(
            select(AssignmentLog).where(AssignmentLog.lead_id == lead.id)
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].reason == "rule_match"
        assert rows[0].assigned_user_id == test_user.id

    @pytest.mark.asyncio
    async def test_create_with_explicit_owner_skips_routing(
        self,
        db_session: AsyncSession,
        test_user: User,
        second_user: User,
    ):
        """Explicit owner_id is honored — routing engine is not consulted."""
        await _add_rule(
            db_session,
            name="would-route-elsewhere",
            user_ids=[second_user.id],
            created_by=test_user.id,
        )

        service = LeadService(db_session)
        lead = await service.create(
            LeadCreate(
                first_name="Manual",
                last_name="Owner",
                status="new",
                owner_id=test_user.id,
            ),
            user_id=test_user.id,
        )

        assert lead.owner_id == test_user.id
        rows = (await db_session.execute(
            select(AssignmentLog).where(AssignmentLog.lead_id == lead.id)
        )).scalars().all()
        assert rows == []

    @pytest.mark.asyncio
    async def test_default_fallback_fires_when_no_filtered_rule_matches(
        self,
        db_session: AsyncSession,
        test_user: User,
        second_user: User,
    ):
        """Filtered rule misses → catch-all `is_default` rule routes the lead."""
        # Filtered rule that won't match (lead has no source_id=42).
        await _add_rule(
            db_session,
            name="picky-source",
            user_ids=[test_user.id],
            filters={"source_id": 42},
            created_by=test_user.id,
        )
        # Catch-all default routes to second_user.
        await _add_rule(
            db_session,
            name="catch-all",
            user_ids=[second_user.id],
            is_default=True,
            created_by=test_user.id,
        )

        service = LeadService(db_session)
        lead = await service.create(
            LeadCreate(first_name="Fallback", last_name="Routed", status="new"),
            user_id=test_user.id,
        )

        assert lead.owner_id == second_user.id
        log_row = (await db_session.execute(
            select(AssignmentLog).where(AssignmentLog.lead_id == lead.id)
        )).scalar_one()
        assert log_row.reason == "default_fallback"

    @pytest.mark.asyncio
    async def test_filtered_rule_wins_over_default_when_both_match(
        self,
        db_session: AsyncSession,
        test_user: User,
        second_user: User,
    ):
        """Filtered rule + default both eligible → filtered wins, default doesn't fire."""
        await _add_rule(
            db_session,
            name="industry-Tech",
            user_ids=[test_user.id],
            filters={"industry": "Tech"},
            created_by=test_user.id,
        )
        await _add_rule(
            db_session,
            name="catch-all",
            user_ids=[second_user.id],
            is_default=True,
            created_by=test_user.id,
        )

        service = LeadService(db_session)
        lead = await service.create(
            LeadCreate(
                first_name="Industry",
                last_name="Match",
                status="new",
                industry="Tech",
            ),
            user_id=test_user.id,
        )

        assert lead.owner_id == test_user.id
        log_row = (await db_session.execute(
            select(AssignmentLog).where(AssignmentLog.lead_id == lead.id)
        )).scalar_one()
        assert log_row.reason == "rule_match"

    @pytest.mark.asyncio
    async def test_no_active_rule_creates_unowned_lead_with_no_log(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """No rules at all → lead lands with owner_id=None and no log row."""
        service = LeadService(db_session)
        lead = await service.create(
            LeadCreate(first_name="Orphan", last_name="Lead", status="new"),
            user_id=test_user.id,
        )

        assert lead.owner_id is None
        rows = (await db_session.execute(
            select(AssignmentLog).where(AssignmentLog.lead_id == lead.id)
        )).scalars().all()
        assert rows == []

    @pytest.mark.asyncio
    async def test_inactive_rule_is_ignored_even_if_default(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """is_default + is_active=False → still skipped."""
        await _add_rule(
            db_session,
            name="inactive default",
            user_ids=[test_user.id],
            is_default=True,
            is_active=False,
            created_by=test_user.id,
        )

        service = LeadService(db_session)
        lead = await service.create(
            LeadCreate(first_name="Skipped", last_name="Default", status="new"),
            user_id=test_user.id,
        )

        assert lead.owner_id is None


class TestRoundRobinTransactionAtomicity:
    """Pins the request-transaction-atomicity contract for round-robin
    index advance. `_get_round_robin_user` flushes (not commits) the
    bumped index, so a request-scope rollback unwinds it. Production
    callers (LeadService.create) run both assign_lead and the lead
    persist in the same request session — a failed lead-create
    rollback reverts the rotation skip.

    DO NOT defer the bump into `log_decision` unless you can guarantee
    callers always run both in the same transaction.
    """

    @pytest.mark.asyncio
    async def test_index_advance_is_undone_by_session_rollback(
        self, db_session: AsyncSession, test_user: User, second_user: User,
    ):
        from src.assignment.service import AssignmentService

        rule = await _add_rule(
            db_session,
            name="rotation rule",
            user_ids=[test_user.id, second_user.id],
            created_by=test_user.id,
        )

        # Pre-flush state
        assert rule.last_assigned_index == -1

        # assign_lead flushes the bump.
        decision = await AssignmentService(db_session).assign_lead({})
        assert decision is not None and decision.user_id == test_user.id
        await db_session.refresh(rule)
        assert rule.last_assigned_index == 0  # flushed

        # Rolling back the session (the production failure path: the
        # request handler raises after assign_lead returned) reverts.
        await db_session.rollback()
        await db_session.refresh(rule)
        assert rule.last_assigned_index == -1


class TestDefaultRulePromotion:
    """The DB enforces 'at most one is_default rule' via a partial
    unique index. AssignmentService.create_rule / update_rule must
    demote the prior default in the same transaction so promoting a
    new one is atomic and never surfaces a raw IntegrityError 500.
    """

    @pytest.mark.asyncio
    async def test_create_default_demotes_prior(
        self, db_session: AsyncSession, test_user: User, second_user: User,
    ):
        from src.assignment.schemas import AssignmentRuleCreate
        from src.assignment.service import AssignmentService

        # Existing default rule.
        old_default = await _add_rule(
            db_session, name="old default",
            user_ids=[test_user.id], is_default=True, created_by=test_user.id,
        )

        # New default created via service — should demote old.
        new_default = await AssignmentService(db_session).create_rule(
            AssignmentRuleCreate(
                name="new default",
                assignment_type="round_robin",
                user_ids=[second_user.id],
                is_default=True,
            ),
            user_id=test_user.id,
        )
        await db_session.commit()
        await db_session.refresh(old_default)
        await db_session.refresh(new_default)

        assert new_default.is_default is True
        assert old_default.is_default is False

    @pytest.mark.asyncio
    async def test_update_to_default_demotes_prior(
        self, db_session: AsyncSession, test_user: User, second_user: User,
    ):
        from src.assignment.schemas import AssignmentRuleUpdate
        from src.assignment.service import AssignmentService

        old_default = await _add_rule(
            db_session, name="old default",
            user_ids=[test_user.id], is_default=True, created_by=test_user.id,
        )
        candidate = await _add_rule(
            db_session, name="candidate",
            user_ids=[second_user.id], is_default=False, created_by=test_user.id,
        )

        promoted = await AssignmentService(db_session).update_rule(
            candidate, AssignmentRuleUpdate(is_default=True),
        )
        await db_session.commit()
        await db_session.refresh(old_default)

        assert promoted.is_default is True
        assert old_default.is_default is False

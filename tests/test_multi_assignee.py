"""Tests for multi-assignee semantics on opportunities and leads.

Verifies that:
- get_list returns records where the user is an assignee (via assignee_entity_ids).
- get_list does NOT return records the user neither owns nor is assigned.
- get_assignee_entity_ids returns only entity IDs with permission_level='assignee'.
- View-only shares are excluded from get_assignee_entity_ids.

These tests use a real in-memory SQLite database; no mocks.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import get_password_hash
from src.core.models import EntityShare
from src.leads.models import Lead, LeadSource
from src.leads.service import LeadService
from src.opportunities.models import Opportunity, PipelineStage
from src.opportunities.service import OpportunityService


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def user_a(db_session: AsyncSession) -> User:
    """Owner user — creates and owns the entities."""
    user = User(
        email="user_a@example.com",
        hashed_password=get_password_hash("pw"),
        full_name="User A",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def user_b(db_session: AsyncSession) -> User:
    """Assignee user — receives an 'assignee' share."""
    user = User(
        email="user_b@example.com",
        hashed_password=get_password_hash("pw"),
        full_name="User B",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def user_c(db_session: AsyncSession) -> User:
    """View-only user — receives a 'view' share (should NOT appear in assignee list)."""
    user = User(
        email="user_c@example.com",
        hashed_password=get_password_hash("pw"),
        full_name="User C",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def pipeline_stage(db_session: AsyncSession) -> PipelineStage:
    stage = PipelineStage(
        name="Discovery",
        order=1,
        color="#06b6d4",
        probability=10,
        is_won=False,
        is_lost=False,
        is_active=True,
        pipeline_type="opportunity",
    )
    db_session.add(stage)
    await db_session.commit()
    await db_session.refresh(stage)
    return stage


@pytest_asyncio.fixture
async def lead_source(db_session: AsyncSession) -> LeadSource:
    source = LeadSource(name="Website", is_active=True)
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


# ---------------------------------------------------------------------------
# Opportunity fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def opportunity_owned_by_a(
    db_session: AsyncSession,
    user_a: User,
    pipeline_stage: PipelineStage,
) -> Opportunity:
    opp = Opportunity(
        name="Opportunity Owned By A",
        pipeline_stage_id=pipeline_stage.id,
        amount=10000.0,
        currency="USD",
        owner_id=user_a.id,
        created_by_id=user_a.id,
    )
    db_session.add(opp)
    await db_session.commit()
    await db_session.refresh(opp)
    return opp


@pytest_asyncio.fixture
async def assignee_share_b_on_opportunity(
    db_session: AsyncSession,
    user_a: User,
    user_b: User,
    opportunity_owned_by_a: Opportunity,
) -> EntityShare:
    """Give user B an 'assignee' share on the opportunity owned by A."""
    share = EntityShare(
        entity_type="opportunities",
        entity_id=opportunity_owned_by_a.id,
        shared_with_user_id=user_b.id,
        shared_by_user_id=user_a.id,
        permission_level="assignee",
    )
    db_session.add(share)
    await db_session.commit()
    await db_session.refresh(share)
    return share


@pytest_asyncio.fixture
async def view_share_c_on_opportunity(
    db_session: AsyncSession,
    user_a: User,
    user_c: User,
    opportunity_owned_by_a: Opportunity,
) -> EntityShare:
    """Give user C a 'view' share on the same opportunity."""
    share = EntityShare(
        entity_type="opportunities",
        entity_id=opportunity_owned_by_a.id,
        shared_with_user_id=user_c.id,
        shared_by_user_id=user_a.id,
        permission_level="view",
    )
    db_session.add(share)
    await db_session.commit()
    await db_session.refresh(share)
    return share


# ---------------------------------------------------------------------------
# Lead fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def lead_owned_by_a(
    db_session: AsyncSession,
    user_a: User,
    lead_source: LeadSource,
) -> Lead:
    lead = Lead(
        first_name="Jane",
        last_name="Smith",
        email="jane.smith@example.com",
        status="new",
        source_id=lead_source.id,
        owner_id=user_a.id,
        created_by_id=user_a.id,
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    return lead


@pytest_asyncio.fixture
async def assignee_share_b_on_lead(
    db_session: AsyncSession,
    user_a: User,
    user_b: User,
    lead_owned_by_a: Lead,
) -> EntityShare:
    """Give user B an 'assignee' share on the lead owned by A."""
    share = EntityShare(
        entity_type="leads",
        entity_id=lead_owned_by_a.id,
        shared_with_user_id=user_b.id,
        shared_by_user_id=user_a.id,
        permission_level="assignee",
    )
    db_session.add(share)
    await db_session.commit()
    await db_session.refresh(share)
    return share


@pytest_asyncio.fixture
async def view_share_c_on_lead(
    db_session: AsyncSession,
    user_a: User,
    user_c: User,
    lead_owned_by_a: Lead,
) -> EntityShare:
    """Give user C a 'view' share on the same lead."""
    share = EntityShare(
        entity_type="leads",
        entity_id=lead_owned_by_a.id,
        shared_with_user_id=user_c.id,
        shared_by_user_id=user_a.id,
        permission_level="view",
    )
    db_session.add(share)
    await db_session.commit()
    await db_session.refresh(share)
    return share


# ===========================================================================
# Opportunity tests
# ===========================================================================

class TestOpportunityMultiAssignee:
    """Multi-assignee semantics for OpportunityService."""

    @pytest.mark.asyncio
    async def test_get_list_with_assignee_entity_ids_returns_assigned_opportunity(
        self,
        db_session: AsyncSession,
        user_b: User,
        opportunity_owned_by_a: Opportunity,
        assignee_share_b_on_opportunity: EntityShare,
    ):
        """get_list returns the opportunity when assignee_entity_ids contains its ID."""
        service = OpportunityService(db_session)
        items, total = await service.get_list(
            owner_id=user_b.id,
            assignee_entity_ids=[opportunity_owned_by_a.id],
        )
        ids = [o.id for o in items]
        assert opportunity_owned_by_a.id in ids
        assert total >= 1

    @pytest.mark.asyncio
    async def test_get_list_without_assignee_ids_excludes_unowned_opportunity(
        self,
        db_session: AsyncSession,
        user_b: User,
        opportunity_owned_by_a: Opportunity,
        assignee_share_b_on_opportunity: EntityShare,
    ):
        """get_list with only owner_id (and no share lists) excludes records B doesn't own."""
        service = OpportunityService(db_session)
        items, total = await service.get_list(
            owner_id=user_b.id,
            assignee_entity_ids=None,
            shared_entity_ids=None,
        )
        ids = [o.id for o in items]
        assert opportunity_owned_by_a.id not in ids
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_assignee_entity_ids_returns_assignee_opportunity(
        self,
        db_session: AsyncSession,
        user_b: User,
        opportunity_owned_by_a: Opportunity,
        assignee_share_b_on_opportunity: EntityShare,
    ):
        """get_assignee_entity_ids returns the opportunity ID for user B."""
        service = OpportunityService(db_session)
        result = await service.get_assignee_entity_ids(user_id=user_b.id)
        assert opportunity_owned_by_a.id in result

    @pytest.mark.asyncio
    async def test_get_assignee_entity_ids_excludes_view_only_shares(
        self,
        db_session: AsyncSession,
        user_c: User,
        opportunity_owned_by_a: Opportunity,
        view_share_c_on_opportunity: EntityShare,
    ):
        """View-only share for user C does NOT appear in get_assignee_entity_ids."""
        service = OpportunityService(db_session)
        result = await service.get_assignee_entity_ids(user_id=user_c.id)
        assert opportunity_owned_by_a.id not in result

    @pytest.mark.asyncio
    async def test_get_list_via_shared_entity_ids_also_works(
        self,
        db_session: AsyncSession,
        user_b: User,
        opportunity_owned_by_a: Opportunity,
        assignee_share_b_on_opportunity: EntityShare,
    ):
        """Backward-compat: assignee IDs passed as shared_entity_ids still surface the record."""
        service = OpportunityService(db_session)
        items, total = await service.get_list(
            owner_id=user_b.id,
            shared_entity_ids=[opportunity_owned_by_a.id],
            assignee_entity_ids=None,
        )
        ids = [o.id for o in items]
        assert opportunity_owned_by_a.id in ids

    @pytest.mark.asyncio
    async def test_get_assignee_entity_ids_empty_for_no_shares(
        self,
        db_session: AsyncSession,
        user_b: User,
        opportunity_owned_by_a: Opportunity,
    ):
        """When no shares exist, get_assignee_entity_ids returns an empty list."""
        service = OpportunityService(db_session)
        result = await service.get_assignee_entity_ids(user_id=user_b.id)
        assert result == []


# ===========================================================================
# Lead tests
# ===========================================================================

class TestLeadMultiAssignee:
    """Multi-assignee semantics for LeadService."""

    @pytest.mark.asyncio
    async def test_get_list_with_assignee_entity_ids_returns_assigned_lead(
        self,
        db_session: AsyncSession,
        user_b: User,
        lead_owned_by_a: Lead,
        assignee_share_b_on_lead: EntityShare,
    ):
        """get_list returns the lead when assignee_entity_ids contains its ID."""
        service = LeadService(db_session)
        items, total = await service.get_list(
            owner_id=user_b.id,
            assignee_entity_ids=[lead_owned_by_a.id],
        )
        ids = [l.id for l in items]
        assert lead_owned_by_a.id in ids
        assert total >= 1

    @pytest.mark.asyncio
    async def test_get_list_without_assignee_ids_excludes_unowned_lead(
        self,
        db_session: AsyncSession,
        user_b: User,
        lead_owned_by_a: Lead,
        assignee_share_b_on_lead: EntityShare,
    ):
        """get_list with only owner_id (and no share lists) excludes leads B doesn't own."""
        service = LeadService(db_session)
        items, total = await service.get_list(
            owner_id=user_b.id,
            assignee_entity_ids=None,
            shared_entity_ids=None,
        )
        ids = [l.id for l in items]
        assert lead_owned_by_a.id not in ids
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_assignee_entity_ids_returns_assignee_lead(
        self,
        db_session: AsyncSession,
        user_b: User,
        lead_owned_by_a: Lead,
        assignee_share_b_on_lead: EntityShare,
    ):
        """get_assignee_entity_ids returns the lead ID for user B."""
        service = LeadService(db_session)
        result = await service.get_assignee_entity_ids(user_id=user_b.id)
        assert lead_owned_by_a.id in result

    @pytest.mark.asyncio
    async def test_get_assignee_entity_ids_excludes_view_only_shares(
        self,
        db_session: AsyncSession,
        user_c: User,
        lead_owned_by_a: Lead,
        view_share_c_on_lead: EntityShare,
    ):
        """View-only share for user C does NOT appear in get_assignee_entity_ids."""
        service = LeadService(db_session)
        result = await service.get_assignee_entity_ids(user_id=user_c.id)
        assert lead_owned_by_a.id not in result

    @pytest.mark.asyncio
    async def test_get_list_via_shared_entity_ids_also_works(
        self,
        db_session: AsyncSession,
        user_b: User,
        lead_owned_by_a: Lead,
        assignee_share_b_on_lead: EntityShare,
    ):
        """Backward-compat: assignee IDs passed as shared_entity_ids still surface the lead."""
        service = LeadService(db_session)
        items, total = await service.get_list(
            owner_id=user_b.id,
            shared_entity_ids=[lead_owned_by_a.id],
            assignee_entity_ids=None,
        )
        ids = [l.id for l in items]
        assert lead_owned_by_a.id in ids

    @pytest.mark.asyncio
    async def test_get_assignee_entity_ids_empty_for_no_shares(
        self,
        db_session: AsyncSession,
        user_b: User,
        lead_owned_by_a: Lead,
    ):
        """When no shares exist, get_assignee_entity_ids returns an empty list."""
        service = LeadService(db_session)
        result = await service.get_assignee_entity_ids(user_id=user_b.id)
        assert result == []

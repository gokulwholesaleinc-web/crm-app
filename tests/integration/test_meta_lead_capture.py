"""Integration tests for Meta Lead Ads → CRM lead conversion.

Exercises `MetaService._create_lead_from_capture`, the function the
webhook handler calls for every captured lead. Real DB, no mocks; we
build `MetaLeadCapture` rows directly so we can skip the OAuth-only
`_fetch_lead_data` HTTP call and focus on the conversion logic.
"""

from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.assignment.models import AssignmentRule
from src.auth.models import User
from src.auth.security import get_password_hash
from src.leads.models import Lead, LeadSource
from src.meta.models import MetaLeadCapture
from src.meta.service import MetaService
from src.opportunities.models import PipelineStage


def _build_raw_data(field_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Mirror the Meta Graph API leadgen response shape."""
    return {
        "id": "leadgen_test_1",
        "created_time": "2026-05-07T12:00:00+0000",
        "field_data": field_data,
    }


@pytest_asyncio.fixture
async def system_admin(db_session: AsyncSession) -> User:
    """An active superuser — webhook attribution falls back to the
    first one of these.
    """
    user = User(
        email="meta-system@example.com",
        hashed_password=get_password_hash("x"),
        full_name="Meta System Admin",
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def lead_pipeline_stage(db_session: AsyncSession) -> PipelineStage:
    """A 'lead' pipeline stage so LeadService.create's auto-backfill
    can populate `pipeline_stage_id` (otherwise it logs a warning).
    """
    stage = PipelineStage(
        name="New Leads",
        description="First-touch leads",
        order=1,
        color="#06b6d4",
        probability=10,
        is_won=False,
        is_lost=False,
        is_active=True,
        pipeline_type="lead",
    )
    db_session.add(stage)
    await db_session.commit()
    await db_session.refresh(stage)
    return stage


async def _make_capture(
    db: AsyncSession,
    *,
    raw_data: dict[str, Any] | None,
    leadgen_id: str = "leadgen_test_1",
    form_id: str = "form_42",
    ad_id: str | None = "ad_99",
) -> MetaLeadCapture:
    capture = MetaLeadCapture(
        form_id=form_id,
        leadgen_id=leadgen_id,
        page_id="page_1",
        ad_id=ad_id,
        raw_data=raw_data,
    )
    db.add(capture)
    await db.commit()
    await db.refresh(capture)
    return capture


class TestMetaLeadConversion:
    """`_create_lead_from_capture` is the entire conversion surface."""

    @pytest.mark.asyncio
    async def test_creates_lead_with_correct_fields(
        self,
        db_session: AsyncSession,
        system_admin: User,
        lead_pipeline_stage: PipelineStage,
    ):
        """Happy path: full Meta payload → Lead with right column names."""
        capture = await _make_capture(
            db_session,
            raw_data=_build_raw_data([
                {"name": "first_name", "values": ["Ada"]},
                {"name": "last_name", "values": ["Lovelace"]},
                {"name": "email", "values": ["ada@example.com"]},
                {"name": "phone_number", "values": ["+1-555-0123"]},
                {"name": "company_name", "values": ["Analytical Engines Ltd"]},
            ]),
        )

        service = MetaService(db_session)
        lead_id = await service._create_lead_from_capture(capture)
        assert lead_id is not None

        lead = (await db_session.execute(
            select(Lead).where(Lead.id == lead_id)
        )).scalar_one()

        assert lead.first_name == "Ada"
        assert lead.last_name == "Lovelace"
        assert lead.email == "ada@example.com"
        assert lead.phone == "+1-555-0123"
        # Critical: column is `company_name`, not `company`.
        assert lead.company_name == "Analytical Engines Ltd"
        assert lead.status == "new"
        # Webhooks are unauthenticated; attribution falls to the
        # system admin so audit trails point somewhere.
        assert lead.created_by_id == system_admin.id
        # New leads stay off-kanban (pipeline_stage_id=NULL) post #328 —
        # admin promotes them into Discovery manually via the quick-edit.
        assert lead.pipeline_stage_id is None

    @pytest.mark.asyncio
    async def test_lead_source_is_meta_lead_ads(
        self,
        db_session: AsyncSession,
        system_admin: User,
    ):
        """source_id (FK) must resolve to a 'Meta Lead Ads' LeadSource
        row, lazy-created on the first capture.
        """
        # Sanity: source doesn't exist yet.
        existing = (await db_session.execute(
            select(LeadSource).where(LeadSource.name == "Meta Lead Ads")
        )).scalar_one_or_none()
        assert existing is None

        capture = await _make_capture(
            db_session,
            raw_data=_build_raw_data([
                {"name": "first_name", "values": ["Grace"]},
                {"name": "last_name", "values": ["Hopper"]},
                {"name": "email", "values": ["grace@example.com"]},
            ]),
        )

        lead_id = await MetaService(db_session)._create_lead_from_capture(capture)
        assert lead_id is not None

        source = (await db_session.execute(
            select(LeadSource).where(LeadSource.name == "Meta Lead Ads")
        )).scalar_one()
        assert source.is_active is True

        lead = (await db_session.execute(
            select(Lead).where(Lead.id == lead_id)
        )).scalar_one()
        assert lead.source_id == source.id

    @pytest.mark.asyncio
    async def test_second_capture_reuses_existing_source(
        self,
        db_session: AsyncSession,
        system_admin: User,
    ):
        """Repeated webhooks must not create duplicate LeadSource rows
        (the column has a unique index — would 500 otherwise).
        """
        for i, leadgen in enumerate(("lg_a", "lg_b")):
            capture = await _make_capture(
                db_session,
                leadgen_id=leadgen,
                raw_data=_build_raw_data([
                    {"name": "first_name", "values": [f"User{i}"]},
                    {"name": "email", "values": [f"user{i}@example.com"]},
                ]),
            )
            await MetaService(db_session)._create_lead_from_capture(capture)

        sources = (await db_session.execute(
            select(LeadSource).where(LeadSource.name == "Meta Lead Ads")
        )).scalars().all()
        assert len(sources) == 1

    @pytest.mark.asyncio
    async def test_full_name_only_splits_into_first_last(
        self,
        db_session: AsyncSession,
        system_admin: User,
    ):
        """Some Meta forms only collect `full_name`. We split on the
        first whitespace so the leads list still shows surname-first
        order correctly.
        """
        capture = await _make_capture(
            db_session,
            raw_data=_build_raw_data([
                {"name": "full_name", "values": ["Katherine Johnson"]},
                {"name": "email", "values": ["katherine@example.com"]},
            ]),
        )

        lead_id = await MetaService(db_session)._create_lead_from_capture(capture)
        assert lead_id is not None
        lead = (await db_session.execute(
            select(Lead).where(Lead.id == lead_id)
        )).scalar_one()
        assert lead.first_name == "Katherine"
        assert lead.last_name == "Johnson"

    @pytest.mark.asyncio
    async def test_full_name_with_three_parts_keeps_remainder_in_last(
        self,
        db_session: AsyncSession,
        system_admin: User,
    ):
        """`split(maxsplit=1)` keeps middle/last together in last_name —
        so "Mary Jackson Smith" → first="Mary", last="Jackson Smith".
        """
        capture = await _make_capture(
            db_session,
            raw_data=_build_raw_data([
                {"name": "full_name", "values": ["Mary Jackson Smith"]},
                {"name": "email", "values": ["mary@example.com"]},
            ]),
        )

        lead_id = await MetaService(db_session)._create_lead_from_capture(capture)
        lead = (await db_session.execute(
            select(Lead).where(Lead.id == lead_id)
        )).scalar_one()
        assert lead.first_name == "Mary"
        assert lead.last_name == "Jackson Smith"

    @pytest.mark.asyncio
    async def test_empty_field_data_does_not_crash(
        self,
        db_session: AsyncSession,
        system_admin: User,
    ):
        """Webhooks have arrived with empty `field_data` (form misconfig).
        We should still create a placeholder lead so the capture isn't
        silently dropped — sales can triage manually.
        """
        capture = await _make_capture(
            db_session,
            raw_data=_build_raw_data([]),
        )

        lead_id = await MetaService(db_session)._create_lead_from_capture(capture)
        assert lead_id is not None

        lead = (await db_session.execute(
            select(Lead).where(Lead.id == lead_id)
        )).scalar_one()
        # Falls back to "Unknown" first_name so the LeadCreate validator
        # (`name OR company_name required`) doesn't reject the row.
        assert lead.first_name == "Unknown"
        assert lead.email is None
        assert lead.phone is None
        assert lead.company_name is None

    @pytest.mark.asyncio
    async def test_phone_field_alias(
        self,
        db_session: AsyncSession,
        system_admin: User,
    ):
        """Meta forms use `phone_number`; legacy/custom forms send
        `phone`. Both should land in Lead.phone.
        """
        capture = await _make_capture(
            db_session,
            raw_data=_build_raw_data([
                {"name": "first_name", "values": ["Alan"]},
                {"name": "phone", "values": ["+44-20-7946-0958"]},
            ]),
        )
        lead_id = await MetaService(db_session)._create_lead_from_capture(capture)
        lead = (await db_session.execute(
            select(Lead).where(Lead.id == lead_id)
        )).scalar_one()
        assert lead.phone == "+44-20-7946-0958"

    @pytest.mark.asyncio
    async def test_no_raw_data_returns_none(
        self,
        db_session: AsyncSession,
        system_admin: User,
    ):
        """A capture with no fetched payload (no META_ACCESS_TOKEN
        configured at webhook time) is a no-op — caller leaves
        `processed=False` so a backfill can retry.
        """
        capture = await _make_capture(db_session, raw_data=None)
        lead_id = await MetaService(db_session)._create_lead_from_capture(capture)
        assert lead_id is None

    @pytest.mark.asyncio
    async def test_no_active_superuser_returns_none(
        self,
        db_session: AsyncSession,
    ):
        """Without an admin to attribute to, we can't satisfy the audit
        log's not-null `created_by_id` — better to skip than 500.
        Capture stays `processed=False` for retry.
        """
        capture = await _make_capture(
            db_session,
            raw_data=_build_raw_data([
                {"name": "first_name", "values": ["Orphan"]},
            ]),
        )
        lead_id = await MetaService(db_session)._create_lead_from_capture(capture)
        assert lead_id is None

        # And no Lead row got created.
        leads = (await db_session.execute(select(Lead))).scalars().all()
        assert leads == []

    @pytest.mark.asyncio
    async def test_description_carries_form_and_ad_ids(
        self,
        db_session: AsyncSession,
        system_admin: User,
    ):
        """Traceability: form_id + ad_id should land in the lead's
        description so attribution survives even if the
        MetaLeadCapture row is later cleaned up.
        """
        capture = await _make_capture(
            db_session,
            form_id="form_xyz",
            ad_id="ad_123",
            raw_data=_build_raw_data([
                {"name": "first_name", "values": ["Trace"]},
            ]),
        )
        lead_id = await MetaService(db_session)._create_lead_from_capture(capture)
        lead = (await db_session.execute(
            select(Lead).where(Lead.id == lead_id)
        )).scalar_one()
        assert lead.description is not None
        assert "form_xyz" in lead.description
        assert "ad_123" in lead.description


class TestMetaLeadAutoAssignment:
    """Cross-feature integration: a Meta-captured lead lands through
    LeadService.create, which now consults the active AssignmentRule
    set. The previous direct-Lead-construction code skipped this hop
    entirely, so meta leads sat unassigned until a human triaged them.
    """

    @pytest.mark.asyncio
    async def test_active_assignment_rule_picks_owner(
        self,
        db_session: AsyncSession,
        system_admin: User,
    ):
        """When an active AssignmentRule exists with at least one user,
        the new lead's owner_id should be one of the rule's users.
        """
        sales_rep = User(
            email="rep1@example.com",
            hashed_password=get_password_hash("x"),
            full_name="Sales Rep One",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(sales_rep)
        await db_session.commit()
        await db_session.refresh(sales_rep)

        rule = AssignmentRule(
            name="Default Meta",
            assignment_type="round_robin",
            user_ids=[sales_rep.id],
            is_active=True,
            is_default=True,
        )
        db_session.add(rule)
        await db_session.commit()

        capture = await _make_capture(
            db_session,
            raw_data=_build_raw_data([
                {"name": "first_name", "values": ["Auto"]},
                {"name": "last_name", "values": ["Assigned"]},
            ]),
        )
        lead_id = await MetaService(db_session)._create_lead_from_capture(capture)
        lead = (await db_session.execute(
            select(Lead).where(Lead.id == lead_id)
        )).scalar_one()
        assert lead.owner_id == sales_rep.id

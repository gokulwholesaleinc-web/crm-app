"""
Tests for seed script functionality.

Validates idempotency, admin account cleanliness, demo data counts,
and authentication for both seeded accounts.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import verify_password, get_password_hash, create_access_token
from src.companies.models import Company
from src.contacts.models import Contact
from src.leads.models import Lead, LeadSource
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.campaigns.models import Campaign
from src.core.models import Note, Tag, EntityTag
from src.seed import seed_database


class TestSeedIdempotency:
    """Verify that running seed_database twice does not duplicate data."""

    @pytest.mark.asyncio
    async def test_seed_is_idempotent(self, db_session: AsyncSession):
        """Running seed_database twice should not duplicate users or demo data."""
        # First run
        await seed_database(db_session)

        # Count entities after first run
        first_user_count = (await db_session.execute(select(func.count(User.id)))).scalar()
        first_company_count = (await db_session.execute(select(func.count(Company.id)))).scalar()
        first_contact_count = (await db_session.execute(select(func.count(Contact.id)))).scalar()
        first_lead_count = (await db_session.execute(select(func.count(Lead.id)))).scalar()
        first_tag_count = (await db_session.execute(select(func.count(Tag.id)))).scalar()
        first_stage_count = (await db_session.execute(select(func.count(PipelineStage.id)))).scalar()
        first_source_count = (await db_session.execute(select(func.count(LeadSource.id)))).scalar()

        # Second run
        await seed_database(db_session)

        # Counts should be identical
        second_user_count = (await db_session.execute(select(func.count(User.id)))).scalar()
        second_company_count = (await db_session.execute(select(func.count(Company.id)))).scalar()
        second_contact_count = (await db_session.execute(select(func.count(Contact.id)))).scalar()
        second_lead_count = (await db_session.execute(select(func.count(Lead.id)))).scalar()
        second_tag_count = (await db_session.execute(select(func.count(Tag.id)))).scalar()
        second_stage_count = (await db_session.execute(select(func.count(PipelineStage.id)))).scalar()
        second_source_count = (await db_session.execute(select(func.count(LeadSource.id)))).scalar()

        assert first_user_count == second_user_count
        assert first_company_count == second_company_count
        assert first_contact_count == second_contact_count
        assert first_lead_count == second_lead_count
        assert first_tag_count == second_tag_count
        assert first_stage_count == second_stage_count
        assert first_source_count == second_source_count


class TestAdminAccount:
    """Verify that admin@admin.com has zero associated data."""

    @pytest_asyncio.fixture(autouse=True)
    async def seed(self, db_session: AsyncSession):
        await seed_database(db_session)

    @pytest.mark.asyncio
    async def test_admin_user_exists(self, db_session: AsyncSession):
        """Admin user should be created with correct attributes."""
        result = await db_session.execute(select(User).where(User.email == "admin@admin.com"))
        admin = result.scalar_one_or_none()

        assert admin is not None
        assert admin.full_name == "Admin User"
        assert admin.is_superuser is True
        assert admin.is_active is True

    @pytest.mark.asyncio
    async def test_admin_password_correct(self, db_session: AsyncSession):
        """Admin password should be admin123."""
        result = await db_session.execute(select(User).where(User.email == "admin@admin.com"))
        admin = result.scalar_one()
        assert verify_password("admin123", admin.hashed_password) is True

    @pytest.mark.asyncio
    async def test_admin_has_zero_companies(self, db_session: AsyncSession):
        """Admin account should have no associated companies."""
        result = await db_session.execute(select(User).where(User.email == "admin@admin.com"))
        admin = result.scalar_one()
        count = (await db_session.execute(
            select(func.count(Company.id)).where(Company.owner_id == admin.id)
        )).scalar()
        assert count == 0

    @pytest.mark.asyncio
    async def test_admin_has_zero_contacts(self, db_session: AsyncSession):
        """Admin account should have no associated contacts."""
        result = await db_session.execute(select(User).where(User.email == "admin@admin.com"))
        admin = result.scalar_one()
        count = (await db_session.execute(
            select(func.count(Contact.id)).where(Contact.owner_id == admin.id)
        )).scalar()
        assert count == 0

    @pytest.mark.asyncio
    async def test_admin_has_zero_leads(self, db_session: AsyncSession):
        """Admin account should have no associated leads."""
        result = await db_session.execute(select(User).where(User.email == "admin@admin.com"))
        admin = result.scalar_one()
        count = (await db_session.execute(
            select(func.count(Lead.id)).where(Lead.owner_id == admin.id)
        )).scalar()
        assert count == 0

    @pytest.mark.asyncio
    async def test_admin_has_zero_opportunities(self, db_session: AsyncSession):
        """Admin account should have no associated opportunities."""
        result = await db_session.execute(select(User).where(User.email == "admin@admin.com"))
        admin = result.scalar_one()
        count = (await db_session.execute(
            select(func.count(Opportunity.id)).where(Opportunity.owner_id == admin.id)
        )).scalar()
        assert count == 0

    @pytest.mark.asyncio
    async def test_admin_has_zero_activities(self, db_session: AsyncSession):
        """Admin account should have no associated activities."""
        result = await db_session.execute(select(User).where(User.email == "admin@admin.com"))
        admin = result.scalar_one()
        count = (await db_session.execute(
            select(func.count(Activity.id)).where(Activity.owner_id == admin.id)
        )).scalar()
        assert count == 0

    @pytest.mark.asyncio
    async def test_admin_has_zero_campaigns(self, db_session: AsyncSession):
        """Admin account should have no associated campaigns."""
        result = await db_session.execute(select(User).where(User.email == "admin@admin.com"))
        admin = result.scalar_one()
        count = (await db_session.execute(
            select(func.count(Campaign.id)).where(Campaign.owner_id == admin.id)
        )).scalar()
        assert count == 0


class TestDemoAccount:
    """Verify that demo@demo.com has the expected amount of seed data."""

    @pytest_asyncio.fixture(autouse=True)
    async def seed(self, db_session: AsyncSession):
        await seed_database(db_session)

    @pytest.mark.asyncio
    async def test_demo_user_exists(self, db_session: AsyncSession):
        """Demo user should be created with correct attributes."""
        result = await db_session.execute(select(User).where(User.email == "demo@demo.com"))
        demo = result.scalar_one_or_none()

        assert demo is not None
        assert demo.full_name == "Demo User"
        assert demo.is_superuser is True
        assert demo.is_active is True

    @pytest.mark.asyncio
    async def test_demo_password_correct(self, db_session: AsyncSession):
        """Demo password should be demo123."""
        result = await db_session.execute(select(User).where(User.email == "demo@demo.com"))
        demo = result.scalar_one()
        assert verify_password("demo123", demo.hashed_password) is True

    @pytest.mark.asyncio
    async def test_demo_has_companies(self, db_session: AsyncSession):
        """Demo account should have 9 companies."""
        result = await db_session.execute(select(User).where(User.email == "demo@demo.com"))
        demo = result.scalar_one()
        count = (await db_session.execute(
            select(func.count(Company.id)).where(Company.owner_id == demo.id)
        )).scalar()
        assert count == 9

    @pytest.mark.asyncio
    async def test_demo_has_contacts(self, db_session: AsyncSession):
        """Demo account should have 23 contacts."""
        result = await db_session.execute(select(User).where(User.email == "demo@demo.com"))
        demo = result.scalar_one()
        count = (await db_session.execute(
            select(func.count(Contact.id)).where(Contact.owner_id == demo.id)
        )).scalar()
        assert count == 23

    @pytest.mark.asyncio
    async def test_demo_has_leads(self, db_session: AsyncSession):
        """Demo account should have 19 leads."""
        result = await db_session.execute(select(User).where(User.email == "demo@demo.com"))
        demo = result.scalar_one()
        count = (await db_session.execute(
            select(func.count(Lead.id)).where(Lead.owner_id == demo.id)
        )).scalar()
        assert count == 19

    @pytest.mark.asyncio
    async def test_demo_has_opportunities(self, db_session: AsyncSession):
        """Demo account should have 12 opportunities."""
        result = await db_session.execute(select(User).where(User.email == "demo@demo.com"))
        demo = result.scalar_one()
        count = (await db_session.execute(
            select(func.count(Opportunity.id)).where(Opportunity.owner_id == demo.id)
        )).scalar()
        assert count == 12

    @pytest.mark.asyncio
    async def test_demo_has_activities(self, db_session: AsyncSession):
        """Demo account should have 35 activities."""
        result = await db_session.execute(select(User).where(User.email == "demo@demo.com"))
        demo = result.scalar_one()
        count = (await db_session.execute(
            select(func.count(Activity.id)).where(Activity.owner_id == demo.id)
        )).scalar()
        assert count == 35

    @pytest.mark.asyncio
    async def test_demo_has_campaigns(self, db_session: AsyncSession):
        """Demo account should have 4 campaigns."""
        result = await db_session.execute(select(User).where(User.email == "demo@demo.com"))
        demo = result.scalar_one()
        count = (await db_session.execute(
            select(func.count(Campaign.id)).where(Campaign.owner_id == demo.id)
        )).scalar()
        assert count == 4

    @pytest.mark.asyncio
    async def test_demo_has_notes(self, db_session: AsyncSession):
        """Demo account should have 14 notes."""
        result = await db_session.execute(select(User).where(User.email == "demo@demo.com"))
        demo = result.scalar_one()
        count = (await db_session.execute(
            select(func.count(Note.id)).where(Note.created_by_id == demo.id)
        )).scalar()
        assert count == 14

    @pytest.mark.asyncio
    async def test_tags_created(self, db_session: AsyncSession):
        """Seed should create 10 tags."""
        count = (await db_session.execute(select(func.count(Tag.id)))).scalar()
        assert count == 10

    @pytest.mark.asyncio
    async def test_entity_tags_created(self, db_session: AsyncSession):
        """Seed should create entity tag assignments."""
        count = (await db_session.execute(select(func.count(EntityTag.id)))).scalar()
        assert count > 0

    @pytest.mark.asyncio
    async def test_pipeline_stages_created(self, db_session: AsyncSession):
        """Seed should create 6 pipeline stages."""
        count = (await db_session.execute(select(func.count(PipelineStage.id)))).scalar()
        assert count == 6

    @pytest.mark.asyncio
    async def test_lead_sources_created(self, db_session: AsyncSession):
        """Seed should create 7 lead sources."""
        count = (await db_session.execute(select(func.count(LeadSource.id)))).scalar()
        assert count == 7

    @pytest.mark.asyncio
    async def test_demo_lead_statuses_varied(self, db_session: AsyncSession):
        """Demo leads should have a mix of statuses."""
        result = await db_session.execute(select(User).where(User.email == "demo@demo.com"))
        demo = result.scalar_one()
        result = await db_session.execute(
            select(Lead.status, func.count(Lead.id))
            .where(Lead.owner_id == demo.id)
            .group_by(Lead.status)
        )
        status_counts = dict(result.all())
        assert "new" in status_counts
        assert "contacted" in status_counts
        assert "qualified" in status_counts
        assert "converted" in status_counts
        assert "lost" in status_counts


class TestSeedAuthentication:
    """Verify that both seeded accounts can authenticate."""

    @pytest_asyncio.fixture(autouse=True)
    async def seed(self, db_session: AsyncSession):
        await seed_database(db_session)

    @pytest.mark.asyncio
    async def test_admin_can_authenticate(self, db_session: AsyncSession):
        """Admin user can authenticate with correct password."""
        from src.auth.service import AuthService

        service = AuthService(db_session)
        user = await service.authenticate_user("admin@admin.com", "admin123")
        assert user is not None
        assert user.email == "admin@admin.com"

    @pytest.mark.asyncio
    async def test_demo_can_authenticate(self, db_session: AsyncSession):
        """Demo user can authenticate with correct password."""
        from src.auth.service import AuthService

        service = AuthService(db_session)
        user = await service.authenticate_user("demo@demo.com", "demo123")
        assert user is not None
        assert user.email == "demo@demo.com"

    @pytest.mark.asyncio
    async def test_admin_wrong_password_fails(self, db_session: AsyncSession):
        """Admin user cannot authenticate with wrong password."""
        from src.auth.service import AuthService

        service = AuthService(db_session)
        user = await service.authenticate_user("admin@admin.com", "wrongpassword")
        assert user is None

    @pytest.mark.asyncio
    async def test_demo_wrong_password_fails(self, db_session: AsyncSession):
        """Demo user cannot authenticate with wrong password."""
        from src.auth.service import AuthService

        service = AuthService(db_session)
        user = await service.authenticate_user("demo@demo.com", "wrongpassword")
        assert user is None

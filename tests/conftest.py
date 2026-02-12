"""
Pytest fixtures for CRM application tests.

Provides async test database setup, test client, and user fixtures.
"""

import asyncio
import sys
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

# Add backend src to path
sys.path.insert(0, "/Users/harshvarma/crm-app/backend")

from src.database import Base, get_db
from src.auth.security import get_password_hash, create_access_token
from src.auth.models import User
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead, LeadSource
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.campaigns.models import Campaign, CampaignMember, EmailTemplate, EmailCampaignStep
from src.core.models import Note, Tag, EntityTag, EntityShare
from src.workflows.models import WorkflowRule, WorkflowExecution
from src.dashboard.models import DashboardNumberCard, DashboardChart
from src.ai.models import AIEmbedding, AIConversation, AIFeedback, AIKnowledgeDocument, AIUserPreferences, AIActionLog, AILearning, AIInteractionLog
from src.whitelabel.models import Tenant, TenantSettings, TenantUser
from src.attachments.models import Attachment
from src.email.models import EmailQueue
from src.notifications.models import Notification
from src.filters.models import SavedFilter
from src.reports.models import SavedReport
from src.audit.models import AuditLog
from src.comments.models import Comment
from src.roles.models import Role, UserRole, RoleName, DEFAULT_PERMISSIONS
from src.webhooks.models import Webhook, WebhookDelivery
from src.assignment.models import AssignmentRule
from src.sequences.models import Sequence, SequenceEnrollment
from src.quotes.models import Quote, QuoteLineItem, QuoteTemplate, ProductBundle, ProductBundleItem
from src.payments.models import StripeCustomer, Product, Price, Payment, Subscription
from src.proposals.models import Proposal, ProposalTemplate, ProposalView


# Test database URL - using SQLite in-memory for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create async test engine with SQLite."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide async database session for tests."""
    async_session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        email="testuser@example.com",
        hashed_password=get_password_hash("testpassword123"),
        full_name="Test User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def test_superuser(db_session: AsyncSession) -> User:
    """Create a test superuser."""
    user = User(
        email="admin@example.com",
        hashed_password=get_password_hash("adminpassword123"),
        full_name="Admin User",
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def auth_token(test_user: User) -> str:
    """Create authentication token for test user."""
    return create_access_token(data={"sub": str(test_user.id)})


@pytest_asyncio.fixture(scope="function")
async def auth_headers(auth_token: str) -> dict:
    """Create authorization headers for API requests."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    from src.main import app

    # Register AI router (normally done in lifespan which doesn't run in tests)
    try:
        from src.ai.router import router as ai_router
        ai_paths = {r.path for r in app.routes if hasattr(r, 'path')}
        if "/api/ai/chat" not in ai_paths:
            app.include_router(ai_router)
    except ImportError:
        pass

    # Override the database dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def test_company(db_session: AsyncSession, test_user: User) -> Company:
    """Create a test company."""
    company = Company(
        name="Test Company Inc",
        website="https://testcompany.com",
        industry="Technology",
        phone="+1-555-0100",
        email="info@testcompany.com",
        city="San Francisco",
        state="CA",
        country="USA",
        status="prospect",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)
    return company


@pytest_asyncio.fixture(scope="function")
async def test_contact(db_session: AsyncSession, test_user: User, test_company: Company) -> Contact:
    """Create a test contact."""
    contact = Contact(
        first_name="John",
        last_name="Doe",
        email="john.doe@testcompany.com",
        phone="+1-555-0101",
        job_title="CEO",
        company_id=test_company.id,
        status="active",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


@pytest_asyncio.fixture(scope="function")
async def test_lead_source(db_session: AsyncSession) -> LeadSource:
    """Create a test lead source."""
    source = LeadSource(
        name="Website",
        description="Leads from website contact form",
        is_active=True,
    )
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest_asyncio.fixture(scope="function")
async def test_lead(db_session: AsyncSession, test_user: User, test_lead_source: LeadSource) -> Lead:
    """Create a test lead."""
    lead = Lead(
        first_name="Jane",
        last_name="Smith",
        email="jane.smith@example.com",
        phone="+1-555-0102",
        company_name="Potential Client LLC",
        industry="Technology",
        source_id=test_lead_source.id,
        status="new",
        score=50,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    return lead


@pytest_asyncio.fixture(scope="function")
async def test_pipeline_stage(db_session: AsyncSession) -> PipelineStage:
    """Create a test pipeline stage."""
    stage = PipelineStage(
        name="Qualification",
        description="Initial qualification stage",
        order=1,
        color="#6366f1",
        probability=20,
        is_won=False,
        is_lost=False,
        is_active=True,
    )
    db_session.add(stage)
    await db_session.commit()
    await db_session.refresh(stage)
    return stage


@pytest_asyncio.fixture(scope="function")
async def test_won_stage(db_session: AsyncSession) -> PipelineStage:
    """Create a won pipeline stage."""
    stage = PipelineStage(
        name="Closed Won",
        description="Deal won",
        order=5,
        color="#22c55e",
        probability=100,
        is_won=True,
        is_lost=False,
        is_active=True,
    )
    db_session.add(stage)
    await db_session.commit()
    await db_session.refresh(stage)
    return stage


@pytest_asyncio.fixture(scope="function")
async def test_opportunity(
    db_session: AsyncSession,
    test_user: User,
    test_pipeline_stage: PipelineStage,
    test_contact: Contact,
    test_company: Company,
) -> Opportunity:
    """Create a test opportunity."""
    from datetime import date, timedelta

    opportunity = Opportunity(
        name="Test Deal",
        description="A test opportunity",
        pipeline_stage_id=test_pipeline_stage.id,
        amount=50000.0,
        currency="USD",
        expected_close_date=date.today() + timedelta(days=30),
        contact_id=test_contact.id,
        company_id=test_company.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(opportunity)
    await db_session.commit()
    await db_session.refresh(opportunity)
    return opportunity


@pytest_asyncio.fixture(scope="function")
async def test_activity(
    db_session: AsyncSession,
    test_user: User,
    test_contact: Contact,
) -> Activity:
    """Create a test activity."""
    from datetime import datetime, timedelta, timezone

    activity = Activity(
        activity_type="call",
        subject="Follow-up call",
        description="Discuss next steps",
        entity_type="contacts",
        entity_id=test_contact.id,
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
        priority="normal",
        is_completed=False,
        owner_id=test_user.id,
        assigned_to_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


@pytest_asyncio.fixture(scope="function")
async def test_tag(db_session: AsyncSession) -> Tag:
    """Create a test tag."""
    tag = Tag(
        name="VIP",
        color="#ef4444",
        description="VIP customer tag",
    )
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)
    return tag


@pytest_asyncio.fixture(scope="function")
async def test_note(db_session: AsyncSession, test_user: User, test_contact: Contact) -> Note:
    """Create a test note."""
    note = Note(
        content="This is a test note",
        entity_type="contact",
        entity_id=test_contact.id,
        created_by_id=test_user.id,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


@pytest_asyncio.fixture(scope="function")
async def test_saved_report(db_session: AsyncSession, test_user: User) -> SavedReport:
    """Create a test saved report."""
    report = SavedReport(
        name="Test Report",
        entity_type="leads",
        metric="count",
        group_by="status",
        chart_type="bar",
        created_by_id=test_user.id,
    )
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    return report


@pytest_asyncio.fixture(scope="function")
async def test_comment(
    db_session: AsyncSession, test_user: User, test_contact: Contact
) -> Comment:
    """Create a test comment."""
    comment = Comment(
        content="This is a test comment @john.doe",
        entity_type="contacts",
        entity_id=test_contact.id,
        user_id=test_user.id,
        is_internal=False,
    )
    db_session.add(comment)
    await db_session.commit()
    await db_session.refresh(comment)
    return comment


@pytest_asyncio.fixture(scope="function")
async def test_tenant(db_session: AsyncSession) -> Tenant:
    """Create a test tenant with settings for use in conftest-level tests."""
    tenant = Tenant(
        name="Test Tenant",
        slug="test-tenant",
        domain="test.example.com",
        is_active=True,
        plan="professional",
        max_users=10,
        max_contacts=1000,
    )
    db_session.add(tenant)
    await db_session.flush()

    settings = TenantSettings(
        tenant_id=tenant.id,
        company_name="Test Tenant Inc",
        logo_url="https://example.com/logo.png",
        favicon_url="https://example.com/favicon.ico",
        primary_color="#6366f1",
        secondary_color="#8b5cf6",
        accent_color="#22c55e",
        footer_text="Test Tenant Footer",
    )
    db_session.add(settings)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture(scope="function")
async def test_tenant_settings(db_session: AsyncSession, test_tenant: Tenant) -> TenantSettings:
    """Get the test tenant's settings."""
    from sqlalchemy import select
    result = await db_session.execute(
        select(TenantSettings).where(TenantSettings.tenant_id == test_tenant.id)
    )
    return result.scalar_one()


@pytest_asyncio.fixture(scope="function")
async def test_tenant_user(
    db_session: AsyncSession, test_tenant: Tenant, test_user: User
) -> TenantUser:
    """Link the test_user to the test_tenant as admin."""
    tenant_user = TenantUser(
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        role="admin",
        is_primary=True,
    )
    db_session.add(tenant_user)
    await db_session.commit()
    await db_session.refresh(tenant_user)
    return tenant_user


# =============================================================================
# RBAC / Role fixtures
# =============================================================================

@pytest_asyncio.fixture(scope="function")
async def seed_roles(db_session: AsyncSession) -> list:
    """Seed default roles (admin, manager, sales_rep, viewer) for tests."""
    roles = []
    for role_name in RoleName:
        role = Role(
            name=role_name.value,
            description=f"Default {role_name.value} role",
            permissions=DEFAULT_PERMISSIONS.get(role_name, {}),
        )
        db_session.add(role)
        roles.append(role)
    await db_session.commit()
    for r in roles:
        await db_session.refresh(r)
    return roles


@pytest_asyncio.fixture(scope="function")
async def test_admin_user(db_session: AsyncSession, seed_roles: list) -> User:
    """Create a test admin user with admin role assigned."""
    user = User(
        email="role_admin@example.com",
        hashed_password=get_password_hash("adminpassword123"),
        full_name="Role Admin User",
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()
    admin_role = next(r for r in seed_roles if r.name == "admin")
    user_role = UserRole(user_id=user.id, role_id=admin_role.id)
    db_session.add(user_role)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def admin_auth_headers(test_admin_user: User) -> dict:
    """Create authorization headers for admin user."""
    token = create_access_token(data={"sub": str(test_admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def _viewer_user(db_session: AsyncSession, seed_roles: list) -> User:
    """Create a test viewer user with viewer role assigned."""
    user = User(
        email="role_viewer@example.com",
        hashed_password=get_password_hash("viewerpassword123"),
        full_name="Viewer User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    viewer_role = next(r for r in seed_roles if r.name == "viewer")
    user_role = UserRole(user_id=user.id, role_id=viewer_role.id)
    db_session.add(user_role)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def viewer_auth_headers(_viewer_user: User) -> dict:
    """Create authorization headers for viewer user."""
    token = create_access_token(data={"sub": str(_viewer_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def _sales_rep_user(db_session: AsyncSession, seed_roles: list) -> User:
    """Create a test sales rep user with sales_rep role assigned."""
    user = User(
        email="role_salesrep@example.com",
        hashed_password=get_password_hash("salesreppassword123"),
        full_name="Sales Rep User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    sales_role = next(r for r in seed_roles if r.name == "sales_rep")
    user_role = UserRole(user_id=user.id, role_id=sales_role.id)
    db_session.add(user_role)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def sales_rep_auth_headers(_sales_rep_user: User) -> dict:
    """Create authorization headers for sales rep user."""
    token = create_access_token(data={"sub": str(_sales_rep_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def _manager_user(db_session: AsyncSession, seed_roles: list) -> User:
    """Create a test manager user with manager role assigned."""
    user = User(
        email="role_manager@example.com",
        hashed_password=get_password_hash("managerpassword123"),
        full_name="Manager User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    manager_role = next(r for r in seed_roles if r.name == "manager")
    user_role = UserRole(user_id=user.id, role_id=manager_role.id)
    db_session.add(user_role)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def manager_auth_headers(_manager_user: User) -> dict:
    """Create authorization headers for manager user."""
    token = create_access_token(data={"sub": str(_manager_user.id)})
    return {"Authorization": f"Bearer {token}"}

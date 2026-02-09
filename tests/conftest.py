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
from src.core.models import Note, Tag, EntityTag
from src.workflows.models import WorkflowRule, WorkflowExecution
from src.audit.models import AuditLog
from src.comments.models import Comment


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
async def test_comment(db_session: AsyncSession, test_user: User, test_contact: Contact) -> Comment:
    """Create a test comment."""
    comment = Comment(
        content="This is a test comment",
        entity_type="contact",
        entity_id=test_contact.id,
        user_id=test_user.id,
        user_name=test_user.full_name,
        user_email=test_user.email,
    )
    db_session.add(comment)
    await db_session.commit()
    await db_session.refresh(comment)
    return comment

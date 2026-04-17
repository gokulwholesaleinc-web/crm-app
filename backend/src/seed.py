"""Seed script for creating demo and admin accounts with realistic CRM data.

Idempotent: safe to run multiple times without duplicating data.
Controlled by SEED_ON_STARTUP env var (default True for dev).
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.activities.models import Activity
from src.auth.models import User
from src.auth.security import get_password_hash
from src.campaigns.models import Campaign
from src.companies.models import Company
from src.contacts.models import Contact
from src.core.models import EntityTag, Note, Tag
from src.leads.models import Lead, LeadSource
from src.opportunities.models import Opportunity, PipelineStage
from src.seed_data import (
    ACTIVITIES_DATA,
    CAMPAIGNS_DATA,
    COMPANIES_DATA,
    CONTACTS_DATA,
    ENTITY_TAG_ASSIGNMENTS,
    LEAD_PIPELINE_STAGES,
    LEAD_SOURCE_NAMES,
    LEADS_DATA,
    NOTES_DATA,
    OPPORTUNITIES_DATA,
    PIPELINE_STAGES,
    TAGS_DATA,
    _today,
)
from src.whitelabel.models import Tenant, TenantSettings, TenantUser


async def seed_database(session: AsyncSession) -> None:
    """Run all seed operations. Idempotent."""
    # Create default tenant first
    tenant = await _seed_default_tenant(session)

    admin = await _seed_admin_user(session)
    demo = await _seed_demo_user(session)

    # Link users to tenant
    if tenant and admin:
        await _link_user_to_tenant(session, admin, tenant, is_primary=True)
    if tenant and demo:
        await _link_user_to_tenant(session, demo, tenant, is_primary=True)

    # Always ensure pipeline stages exist (even for existing databases)
    stages = await _seed_pipeline_stages(session)
    lead_stages = await _seed_lead_pipeline_stages(session)

    if demo is None:
        # demo user already existed, skip data seeding
        await session.commit()
        return

    # Seed lead sources
    lead_sources = await _seed_lead_sources(session)

    # Seed demo data linked to demo user
    companies = await _seed_companies(session, demo)
    contacts = await _seed_contacts(session, demo, companies)
    leads = await _seed_leads(session, demo, lead_sources, lead_stages)
    opportunities = await _seed_opportunities(session, demo, stages, contacts, companies)
    await _seed_activities(session, demo, contacts, leads, opportunities)
    campaigns = await _seed_campaigns(session, demo)
    await _seed_notes(session, demo, contacts, leads, opportunities)
    tags = await _seed_tags(session)
    await _seed_entity_tags(session, tags, contacts, leads, opportunities, companies)

    await session.commit()
    print("Seed data created successfully")


# ---------------------------------------------------------------------------
# Admin account
# ---------------------------------------------------------------------------

async def _seed_admin_user(session: AsyncSession) -> User:
    """Create admin@admin.com if it does not exist."""
    result = await session.execute(select(User).where(User.email == "admin@admin.com"))
    existing = result.scalar_one_or_none()
    if existing:
        print("Admin user already exists, skipping")
        return existing

    user = User(
        email="admin@admin.com",
        hashed_password=get_password_hash("admin123"),
        full_name="Admin User",
        is_active=True,
        is_superuser=True,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    print("Admin user created: admin@admin.com / admin123")
    return user


# ---------------------------------------------------------------------------
# Demo account
# ---------------------------------------------------------------------------

async def _seed_demo_user(session: AsyncSession) -> User | None:
    """Create demo@demo.com if it does not exist. Returns None if already seeded."""
    result = await session.execute(select(User).where(User.email == "demo@demo.com"))
    existing = result.scalar_one_or_none()
    if existing:
        print("Demo user already exists, skipping all demo data")
        return None

    user = User(
        email="demo@demo.com",
        hashed_password=get_password_hash("demo123"),
        full_name="Demo User",
        is_active=True,
        is_superuser=True,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    print("Demo user created: demo@demo.com / demo123")
    return user


# ---------------------------------------------------------------------------
# Default Tenant
# ---------------------------------------------------------------------------

async def _seed_default_tenant(session: AsyncSession) -> Tenant:
    """Create default tenant if it does not exist."""
    result = await session.execute(select(Tenant).where(Tenant.slug == "default"))
    existing = result.scalar_one_or_none()
    if existing:
        print("Default tenant already exists, skipping")
        return existing

    tenant = Tenant(
        name="Default Organization",
        slug="default",
        is_active=True,
        plan="professional",
        max_users=50,
        max_contacts=10000,
    )
    session.add(tenant)
    await session.flush()
    await session.refresh(tenant)

    # Create tenant settings
    settings = TenantSettings(
        tenant_id=tenant.id,
        company_name="CRM App",
        primary_color="#6366f1",
        secondary_color="#8b5cf6",
        accent_color="#06b6d4",
    )
    session.add(settings)
    await session.flush()

    print("Default tenant created: default")
    return tenant


async def _link_user_to_tenant(
    session: AsyncSession, user: User, tenant: Tenant, is_primary: bool = False
) -> None:
    """Link a user to a tenant if not already linked."""
    result = await session.execute(
        select(TenantUser).where(
            TenantUser.user_id == user.id, TenantUser.tenant_id == tenant.id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return

    tenant_user = TenantUser(
        user_id=user.id,
        tenant_id=tenant.id,
        role="admin",
        is_primary=is_primary,
    )
    session.add(tenant_user)
    await session.flush()


# ---------------------------------------------------------------------------
# Pipeline stages (shared)
# ---------------------------------------------------------------------------

async def _seed_pipeline_stages(session: AsyncSession) -> list[PipelineStage]:
    """Create default opportunity pipeline stages if none exist."""
    result = await session.execute(
        select(PipelineStage).where(PipelineStage.pipeline_type == "opportunity")
    )
    existing = list(result.scalars().all())
    if existing:
        return existing

    stages = []
    for s in PIPELINE_STAGES:
        stage = PipelineStage(**s, is_active=True)
        session.add(stage)
        stages.append(stage)
    await session.flush()
    for s in stages:
        await session.refresh(s)
    return stages


async def _seed_lead_pipeline_stages(session: AsyncSession) -> list[PipelineStage]:
    """Create default lead pipeline stages if none exist."""
    result = await session.execute(
        select(PipelineStage).where(PipelineStage.pipeline_type == "lead")
    )
    existing = list(result.scalars().all())
    if existing:
        return existing

    stages = []
    for s in LEAD_PIPELINE_STAGES:
        data = {"is_won": False, "is_lost": False, **s}
        stage = PipelineStage(**data, is_active=True)
        session.add(stage)
        stages.append(stage)
    await session.flush()
    for s in stages:
        await session.refresh(s)
    return stages


# ---------------------------------------------------------------------------
# Lead sources
# ---------------------------------------------------------------------------

async def _seed_lead_sources(session: AsyncSession) -> list[LeadSource]:
    """Create default lead sources if none exist."""
    result = await session.execute(select(LeadSource))
    existing = list(result.scalars().all())
    if existing:
        return existing

    sources = []
    for name in LEAD_SOURCE_NAMES:
        src = LeadSource(name=name, is_active=True)
        session.add(src)
        sources.append(src)
    await session.flush()
    for s in sources:
        await session.refresh(s)
    return sources


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

async def _seed_companies(session: AsyncSession, demo_user: User) -> list[Company]:
    companies = []
    for data in COMPANIES_DATA:
        company = Company(**data, owner_id=demo_user.id, created_by_id=demo_user.id)
        session.add(company)
        companies.append(company)
    await session.flush()
    for c in companies:
        await session.refresh(c)
    return companies


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

async def _seed_contacts(session: AsyncSession, demo_user: User, companies: list[Company]) -> list[Contact]:
    contacts = []
    for raw in CONTACTS_DATA:
        data = dict(raw)
        idx = data.pop("company_idx")
        company_id = companies[idx].id if idx is not None else None
        contact = Contact(**data, company_id=company_id, owner_id=demo_user.id, created_by_id=demo_user.id)
        session.add(contact)
        contacts.append(contact)
    await session.flush()
    for c in contacts:
        await session.refresh(c)
    return contacts


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------

async def _seed_leads(session: AsyncSession, demo_user: User, lead_sources: list[LeadSource], lead_stages: list[PipelineStage] = None) -> list[Lead]:
    source_map = {s.name: s.id for s in lead_sources}

    # Build status-to-stage mapping for lead pipeline stages
    status_stage_map = {}
    if lead_stages:
        stage_name_map = {s.name.lower(): s.id for s in lead_stages}
        status_stage_map = {
            "new": stage_name_map.get("discovery"),
            "contacted": stage_name_map.get("discovery"),
            "qualified": stage_name_map.get("proposal"),
            "unqualified": stage_name_map.get("stalling"),
            "converted": stage_name_map.get("won"),
            "lost": stage_name_map.get("lost"),
        }

    leads = []
    for raw in LEADS_DATA:
        data = dict(raw)
        source_name = data.pop("source_name")
        status = data.get("status", "new")
        pipeline_stage_id = status_stage_map.get(status)
        lead = Lead(
            **data,
            source_id=source_map.get(source_name),
            pipeline_stage_id=pipeline_stage_id,
            owner_id=demo_user.id,
            created_by_id=demo_user.id,
        )
        session.add(lead)
        leads.append(lead)
    await session.flush()
    for l in leads:
        await session.refresh(l)
    return leads


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------

async def _seed_opportunities(
    session: AsyncSession,
    demo_user: User,
    stages: list[PipelineStage],
    contacts: list[Contact],
    companies: list[Company],
) -> list[Opportunity]:
    stage_map = {s.name: s.id for s in stages}
    today = _today()
    opportunities = []
    for raw in OPPORTUNITIES_DATA:
        data = dict(raw)
        stage_name = data.pop("stage_name")
        days = data.pop("days_to_close")
        contact_idx = data.pop("contact_idx")
        company_idx = data.pop("company_idx")

        stage_id = stage_map.get(stage_name)
        if not stage_id:
            continue

        close_date = today + timedelta(days=days)
        actual_close = close_date if days < 0 else None

        opp = Opportunity(
            **data,
            pipeline_stage_id=stage_id,
            expected_close_date=close_date,
            actual_close_date=actual_close,
            currency="USD",
            contact_id=contacts[contact_idx].id,
            company_id=companies[company_idx].id,
            owner_id=demo_user.id,
            created_by_id=demo_user.id,
            loss_reason="Price" if stage_name == "Lost" and "competitor" in data.get("description", "").lower() else ("Budget" if stage_name == "Lost" else None),
        )
        session.add(opp)
        opportunities.append(opp)
    await session.flush()
    for o in opportunities:
        await session.refresh(o)
    return opportunities


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

async def _seed_activities(
    session: AsyncSession,
    demo_user: User,
    contacts: list[Contact],
    leads: list[Lead],
    opportunities: list[Opportunity],
) -> list[Activity]:
    entity_lists = {
        "contacts": contacts,
        "leads": leads,
        "opportunities": opportunities,
    }
    activities = []
    for raw in ACTIVITIES_DATA:
        data = dict(raw)
        entity_type = data.pop("entity_type")
        entity_idx = data.pop("entity_idx")
        entity_id = entity_lists[entity_type][entity_idx].id

        # Set completed_at for completed activities
        completed_at = data.get("scheduled_at") if data.get("is_completed") else None
        due_date = data.pop("due_date", None)

        activity = Activity(
            **data,
            entity_type=entity_type,
            entity_id=entity_id,
            completed_at=completed_at,
            due_date=due_date,
            owner_id=demo_user.id,
            assigned_to_id=demo_user.id,
            created_by_id=demo_user.id,
        )
        session.add(activity)
        activities.append(activity)
    await session.flush()
    for a in activities:
        await session.refresh(a)
    return activities


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

async def _seed_campaigns(session: AsyncSession, demo_user: User) -> list[Campaign]:
    campaigns = []
    for data in CAMPAIGNS_DATA:
        campaign = Campaign(**data, owner_id=demo_user.id, created_by_id=demo_user.id)
        session.add(campaign)
        campaigns.append(campaign)
    await session.flush()
    for c in campaigns:
        await session.refresh(c)
    return campaigns


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

async def _seed_notes(
    session: AsyncSession,
    demo_user: User,
    contacts: list[Contact],
    leads: list[Lead],
    opportunities: list[Opportunity],
) -> list[Note]:
    # We also need companies for notes that reference companies
    # companies are passed via the contacts' company references, but we can use the global data
    # Actually let's just accept companies too. We'll read from the outer scope via a workaround.
    # For simplicity, let's query companies
    result = await session.execute(select(Company).where(Company.owner_id == demo_user.id))
    companies = list(result.scalars().all())

    entity_lists = {
        "contacts": contacts,
        "leads": leads,
        "opportunities": opportunities,
        "companies": companies,
    }
    notes = []
    for data in NOTES_DATA:
        entity_type = data["entity_type"]
        entity_idx = data["entity_idx"]
        list_key = data["list_key"]
        content = data["content"]
        entity_id = entity_lists[list_key][entity_idx].id

        note = Note(
            content=content,
            entity_type=entity_type,
            entity_id=entity_id,
            created_by_id=demo_user.id,
        )
        session.add(note)
        notes.append(note)
    await session.flush()
    for n in notes:
        await session.refresh(n)
    return notes


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

async def _seed_tags(session: AsyncSession) -> list[Tag]:
    result = await session.execute(select(Tag))
    existing = list(result.scalars().all())
    if existing:
        return existing

    tags = []
    for data in TAGS_DATA:
        tag = Tag(**data)
        session.add(tag)
        tags.append(tag)
    await session.flush()
    for t in tags:
        await session.refresh(t)
    return tags


# ---------------------------------------------------------------------------
# Entity Tags (applying tags to various entities)
# ---------------------------------------------------------------------------

async def _seed_entity_tags(
    session: AsyncSession,
    tags: list[Tag],
    contacts: list[Contact],
    leads: list[Lead],
    opportunities: list[Opportunity],
    companies: list[Company],
) -> None:
    entity_lists = {
        "contacts": contacts,
        "leads": leads,
        "opportunities": opportunities,
        "companies": companies,
    }
    for assignment in ENTITY_TAG_ASSIGNMENTS:
        tag = tags[assignment["tag_idx"]]
        entity_type = assignment["entity_type"]
        list_key = assignment["list_key"]
        entity_idx = assignment["entity_idx"]
        entity_id = entity_lists[list_key][entity_idx].id

        et = EntityTag(
            tag_id=tag.id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        session.add(et)
    await session.flush()

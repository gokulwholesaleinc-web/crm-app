"""Seed script for creating demo and admin accounts with realistic CRM data.

Idempotent: safe to run multiple times without duplicating data.
Controlled by SEED_ON_STARTUP env var (default True for dev).
"""

import os
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import get_password_hash
from src.companies.models import Company
from src.contacts.models import Contact
from src.leads.models import Lead, LeadSource
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.campaigns.models import Campaign
from src.core.models import Note, Tag, EntityTag


async def seed_database(session: AsyncSession) -> None:
    """Run all seed operations. Idempotent."""
    admin = await _seed_admin_user(session)
    demo = await _seed_demo_user(session)
    if demo is None:
        # demo user already existed, skip data seeding
        await session.commit()
        return

    # Seed pipeline stages first (needed by opportunities)
    stages = await _seed_pipeline_stages(session)

    # Seed lead sources
    lead_sources = await _seed_lead_sources(session)

    # Seed demo data linked to demo user
    companies = await _seed_companies(session, demo)
    contacts = await _seed_contacts(session, demo, companies)
    leads = await _seed_leads(session, demo, lead_sources)
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
        role="admin",
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
        role="admin",
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    print("Demo user created: demo@demo.com / demo123")
    return user


# ---------------------------------------------------------------------------
# Pipeline stages (shared)
# ---------------------------------------------------------------------------

PIPELINE_STAGES = [
    {"name": "Prospecting", "order": 1, "color": "#94a3b8", "probability": 10, "is_won": False, "is_lost": False},
    {"name": "Qualification", "order": 2, "color": "#60a5fa", "probability": 20, "is_won": False, "is_lost": False},
    {"name": "Proposal", "order": 3, "color": "#818cf8", "probability": 40, "is_won": False, "is_lost": False},
    {"name": "Negotiation", "order": 4, "color": "#f59e0b", "probability": 60, "is_won": False, "is_lost": False},
    {"name": "Closed Won", "order": 5, "color": "#22c55e", "probability": 100, "is_won": True, "is_lost": False},
    {"name": "Closed Lost", "order": 6, "color": "#ef4444", "probability": 0, "is_won": False, "is_lost": True},
]


async def _seed_pipeline_stages(session: AsyncSession) -> list[PipelineStage]:
    """Create default pipeline stages if none exist."""
    result = await session.execute(select(PipelineStage))
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


# ---------------------------------------------------------------------------
# Lead sources
# ---------------------------------------------------------------------------

LEAD_SOURCE_NAMES = ["Website", "Referral", "LinkedIn", "Cold Call", "Trade Show", "Webinar", "Partner"]


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

COMPANIES_DATA = [
    {
        "name": "Acme Technologies",
        "website": "https://acmetech.io",
        "industry": "Technology",
        "company_size": "51-200",
        "phone": "+1-415-555-0110",
        "email": "info@acmetech.io",
        "address_line1": "100 Market Street",
        "city": "San Francisco",
        "state": "CA",
        "postal_code": "94105",
        "country": "USA",
        "annual_revenue": 12000000,
        "employee_count": 120,
        "status": "customer",
        "description": "Enterprise SaaS platform for workflow automation.",
    },
    {
        "name": "Horizon Healthcare",
        "website": "https://horizonhc.com",
        "industry": "Healthcare",
        "company_size": "201-500",
        "phone": "+1-617-555-0120",
        "email": "contact@horizonhc.com",
        "address_line1": "200 Beacon Street",
        "city": "Boston",
        "state": "MA",
        "postal_code": "02116",
        "country": "USA",
        "annual_revenue": 45000000,
        "employee_count": 340,
        "status": "customer",
        "description": "Digital health platform connecting patients with providers.",
    },
    {
        "name": "Summit Financial Group",
        "website": "https://summitfg.com",
        "industry": "Finance",
        "company_size": "501-1000",
        "phone": "+1-212-555-0130",
        "email": "info@summitfg.com",
        "address_line1": "350 Park Avenue",
        "city": "New York",
        "state": "NY",
        "postal_code": "10022",
        "country": "USA",
        "annual_revenue": 82000000,
        "employee_count": 680,
        "status": "prospect",
        "description": "Full-service wealth management and advisory firm.",
    },
    {
        "name": "Nova Retail",
        "website": "https://novaretail.co",
        "industry": "Retail",
        "company_size": "51-200",
        "phone": "+1-312-555-0140",
        "email": "hello@novaretail.co",
        "address_line1": "500 Michigan Avenue",
        "city": "Chicago",
        "state": "IL",
        "postal_code": "60611",
        "country": "USA",
        "annual_revenue": 8500000,
        "employee_count": 95,
        "status": "prospect",
        "description": "D2C fashion brand with brick-and-mortar and e-commerce presence.",
    },
    {
        "name": "Pinnacle Software",
        "website": "https://pinnaclesoft.com",
        "industry": "Technology",
        "company_size": "11-50",
        "phone": "+1-503-555-0150",
        "email": "team@pinnaclesoft.com",
        "address_line1": "900 SW Washington",
        "city": "Portland",
        "state": "OR",
        "postal_code": "97205",
        "country": "USA",
        "annual_revenue": 3200000,
        "employee_count": 28,
        "status": "customer",
        "description": "Custom software development and consulting firm.",
    },
    {
        "name": "Vertex Solutions",
        "website": "https://vertexsol.com",
        "industry": "Consulting",
        "company_size": "201-500",
        "phone": "+1-404-555-0160",
        "email": "inquiries@vertexsol.com",
        "address_line1": "1200 Peachtree Street",
        "city": "Atlanta",
        "state": "GA",
        "postal_code": "30309",
        "country": "USA",
        "annual_revenue": 25000000,
        "employee_count": 210,
        "status": "prospect",
        "description": "Management consulting and digital transformation services.",
    },
    {
        "name": "Cascade Analytics",
        "website": "https://cascadeanalytics.io",
        "industry": "Technology",
        "company_size": "11-50",
        "phone": "+1-206-555-0170",
        "email": "info@cascadeanalytics.io",
        "address_line1": "700 Pike Street",
        "city": "Seattle",
        "state": "WA",
        "postal_code": "98101",
        "country": "USA",
        "annual_revenue": 5800000,
        "employee_count": 42,
        "status": "customer",
        "description": "AI-powered business intelligence and data analytics platform.",
    },
    {
        "name": "Meridian Corp",
        "website": "https://meridiancorp.com",
        "industry": "Manufacturing",
        "company_size": "501-1000",
        "phone": "+1-313-555-0180",
        "email": "sales@meridiancorp.com",
        "address_line1": "2500 Woodward Avenue",
        "city": "Detroit",
        "state": "MI",
        "postal_code": "48201",
        "country": "USA",
        "annual_revenue": 64000000,
        "employee_count": 520,
        "status": "prospect",
        "description": "Precision manufacturing for automotive and aerospace sectors.",
    },
    {
        "name": "Brightpath Education",
        "website": "https://brightpathedu.com",
        "industry": "Education",
        "company_size": "51-200",
        "phone": "+1-512-555-0190",
        "email": "hello@brightpathedu.com",
        "address_line1": "800 Congress Avenue",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78701",
        "country": "USA",
        "annual_revenue": 9200000,
        "employee_count": 75,
        "status": "customer",
        "description": "Online learning platform for professional certification programs.",
    },
]


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

CONTACTS_DATA = [
    # Acme Technologies (index 0)
    {"first_name": "Sarah", "last_name": "Chen", "email": "sarah.chen@acmetech.io", "phone": "+1-415-555-1001", "job_title": "CEO", "department": "Executive", "city": "San Francisco", "state": "CA", "country": "USA", "status": "active", "company_idx": 0},
    {"first_name": "Marcus", "last_name": "Johnson", "email": "m.johnson@acmetech.io", "phone": "+1-415-555-1002", "job_title": "CTO", "department": "Engineering", "city": "San Francisco", "state": "CA", "country": "USA", "status": "active", "company_idx": 0},
    {"first_name": "Lisa", "last_name": "Park", "email": "lisa.park@acmetech.io", "phone": "+1-415-555-1003", "job_title": "VP of Sales", "department": "Sales", "city": "San Francisco", "state": "CA", "country": "USA", "status": "active", "company_idx": 0},
    # Horizon Healthcare (index 1)
    {"first_name": "Dr. Robert", "last_name": "Williams", "email": "r.williams@horizonhc.com", "phone": "+1-617-555-2001", "job_title": "Chief Medical Officer", "department": "Medical", "city": "Boston", "state": "MA", "country": "USA", "status": "active", "company_idx": 1},
    {"first_name": "Angela", "last_name": "Martinez", "email": "a.martinez@horizonhc.com", "phone": "+1-617-555-2002", "job_title": "VP of Operations", "department": "Operations", "city": "Boston", "state": "MA", "country": "USA", "status": "active", "company_idx": 1},
    # Summit Financial Group (index 2)
    {"first_name": "James", "last_name": "Thornton", "email": "j.thornton@summitfg.com", "phone": "+1-212-555-3001", "job_title": "Managing Director", "department": "Executive", "city": "New York", "state": "NY", "country": "USA", "status": "active", "company_idx": 2},
    {"first_name": "Emily", "last_name": "Davis", "email": "e.davis@summitfg.com", "phone": "+1-212-555-3002", "job_title": "Head of Technology", "department": "IT", "city": "New York", "state": "NY", "country": "USA", "status": "active", "company_idx": 2},
    {"first_name": "Michael", "last_name": "Ross", "email": "m.ross@summitfg.com", "phone": "+1-212-555-3003", "job_title": "Portfolio Manager", "department": "Investments", "city": "New York", "state": "NY", "country": "USA", "status": "active", "company_idx": 2},
    # Nova Retail (index 3)
    {"first_name": "Priya", "last_name": "Sharma", "email": "priya@novaretail.co", "phone": "+1-312-555-4001", "job_title": "Founder & CEO", "department": "Executive", "city": "Chicago", "state": "IL", "country": "USA", "status": "active", "company_idx": 3},
    {"first_name": "David", "last_name": "Kim", "email": "d.kim@novaretail.co", "phone": "+1-312-555-4002", "job_title": "Marketing Director", "department": "Marketing", "city": "Chicago", "state": "IL", "country": "USA", "status": "active", "company_idx": 3},
    # Pinnacle Software (index 4)
    {"first_name": "Tom", "last_name": "Bradley", "email": "tom@pinnaclesoft.com", "phone": "+1-503-555-5001", "job_title": "Co-Founder", "department": "Executive", "city": "Portland", "state": "OR", "country": "USA", "status": "active", "company_idx": 4},
    {"first_name": "Rachel", "last_name": "Green", "email": "rachel@pinnaclesoft.com", "phone": "+1-503-555-5002", "job_title": "Lead Architect", "department": "Engineering", "city": "Portland", "state": "OR", "country": "USA", "status": "active", "company_idx": 4},
    # Vertex Solutions (index 5)
    {"first_name": "Kevin", "last_name": "O'Brien", "email": "k.obrien@vertexsol.com", "phone": "+1-404-555-6001", "job_title": "Senior Partner", "department": "Consulting", "city": "Atlanta", "state": "GA", "country": "USA", "status": "active", "company_idx": 5},
    {"first_name": "Diana", "last_name": "Foster", "email": "d.foster@vertexsol.com", "phone": "+1-404-555-6002", "job_title": "Director of Strategy", "department": "Strategy", "city": "Atlanta", "state": "GA", "country": "USA", "status": "active", "company_idx": 5},
    # Cascade Analytics (index 6)
    {"first_name": "Alex", "last_name": "Nguyen", "email": "alex@cascadeanalytics.io", "phone": "+1-206-555-7001", "job_title": "CEO", "department": "Executive", "city": "Seattle", "state": "WA", "country": "USA", "status": "active", "company_idx": 6},
    {"first_name": "Samantha", "last_name": "Lee", "email": "s.lee@cascadeanalytics.io", "phone": "+1-206-555-7002", "job_title": "Head of Product", "department": "Product", "city": "Seattle", "state": "WA", "country": "USA", "status": "active", "company_idx": 6},
    # Meridian Corp (index 7)
    {"first_name": "Robert", "last_name": "Hayes", "email": "r.hayes@meridiancorp.com", "phone": "+1-313-555-8001", "job_title": "VP of Procurement", "department": "Procurement", "city": "Detroit", "state": "MI", "country": "USA", "status": "active", "company_idx": 7},
    {"first_name": "Catherine", "last_name": "Moore", "email": "c.moore@meridiancorp.com", "phone": "+1-313-555-8002", "job_title": "IT Director", "department": "IT", "city": "Detroit", "state": "MI", "country": "USA", "status": "active", "company_idx": 7},
    # Brightpath Education (index 8)
    {"first_name": "Nathan", "last_name": "Wright", "email": "n.wright@brightpathedu.com", "phone": "+1-512-555-9001", "job_title": "CTO", "department": "Engineering", "city": "Austin", "state": "TX", "country": "USA", "status": "active", "company_idx": 8},
    {"first_name": "Olivia", "last_name": "Taylor", "email": "o.taylor@brightpathedu.com", "phone": "+1-512-555-9002", "job_title": "Head of Partnerships", "department": "Business Development", "city": "Austin", "state": "TX", "country": "USA", "status": "active", "company_idx": 8},
    # Additional contacts without companies
    {"first_name": "Daniel", "last_name": "Patel", "email": "d.patel@outlook.com", "phone": "+1-650-555-0201", "job_title": "Freelance Consultant", "department": None, "city": "Palo Alto", "state": "CA", "country": "USA", "status": "active", "company_idx": None},
    {"first_name": "Michelle", "last_name": "Gomez", "email": "m.gomez@gmail.com", "phone": "+1-310-555-0202", "job_title": "Independent Advisor", "department": None, "city": "Los Angeles", "state": "CA", "country": "USA", "status": "inactive", "company_idx": None},
    {"first_name": "Brian", "last_name": "Cooper", "email": "b.cooper@yahoo.com", "phone": "+1-720-555-0203", "job_title": "Startup Founder", "department": None, "city": "Denver", "state": "CO", "country": "USA", "status": "active", "company_idx": None},
]


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

LEADS_DATA = [
    # New leads (5)
    {"first_name": "Ryan", "last_name": "Mitchell", "email": "ryan.mitchell@techflow.io", "phone": "+1-408-555-3001", "company_name": "TechFlow Inc", "industry": "Technology", "source_name": "Website", "status": "new", "score": 45, "job_title": "Engineering Manager", "description": "Interested in enterprise automation tools."},
    {"first_name": "Jennifer", "last_name": "Cruz", "email": "j.cruz@globalmed.com", "phone": "+1-858-555-3002", "company_name": "GlobalMed Systems", "industry": "Healthcare", "source_name": "LinkedIn", "status": "new", "score": 62, "job_title": "VP of Operations", "description": "Looking for patient management solution."},
    {"first_name": "Ahmad", "last_name": "Hassan", "email": "a.hassan@rapidgrowth.co", "phone": "+1-305-555-3003", "company_name": "Rapid Growth Ventures", "industry": "Finance", "source_name": "Trade Show", "status": "new", "score": 38, "job_title": "Investment Analyst", "description": "Met at FinTech Summit 2025."},
    {"first_name": "Laura", "last_name": "Bennett", "email": "l.bennett@cloudsync.com", "phone": "+1-425-555-3004", "company_name": "CloudSync Solutions", "industry": "Technology", "source_name": "Webinar", "status": "new", "score": 71, "job_title": "Director of IT", "description": "Attended our cloud migration webinar."},
    {"first_name": "Carlos", "last_name": "Reyes", "email": "c.reyes@buildright.com", "phone": "+1-602-555-3005", "company_name": "BuildRight Construction", "industry": "Construction", "source_name": "Referral", "status": "new", "score": 29, "job_title": "Operations Director", "description": "Referred by existing customer Tom Bradley."},
    # Contacted (4)
    {"first_name": "Sophie", "last_name": "Anderson", "email": "s.anderson@datadriven.ai", "phone": "+1-628-555-3006", "company_name": "DataDriven AI", "industry": "Technology", "source_name": "Website", "status": "contacted", "score": 55, "job_title": "Head of Data", "description": "Requested pricing info via website."},
    {"first_name": "Patrick", "last_name": "Murphy", "email": "p.murphy@tradewise.com", "phone": "+1-646-555-3007", "company_name": "TradeWise Capital", "industry": "Finance", "source_name": "Cold Call", "status": "contacted", "score": 48, "job_title": "Managing Partner", "description": "Initial cold call went well, scheduling follow-up."},
    {"first_name": "Yuki", "last_name": "Tanaka", "email": "y.tanaka@zenith.jp", "phone": "+1-415-555-3008", "company_name": "Zenith Japan Corp", "industry": "Manufacturing", "source_name": "Trade Show", "status": "contacted", "score": 67, "job_title": "Business Development", "description": "Interested in US market expansion tools."},
    {"first_name": "Maria", "last_name": "Santos", "email": "m.santos@greenleaf.co", "phone": "+1-503-555-3009", "company_name": "GreenLeaf Organics", "industry": "Retail", "source_name": "Partner", "status": "contacted", "score": 52, "job_title": "CEO", "description": "Partner referral from Vertex Solutions."},
    # Qualified (3)
    {"first_name": "Chris", "last_name": "Walker", "email": "c.walker@logicgate.io", "phone": "+1-312-555-3010", "company_name": "LogicGate Systems", "industry": "Technology", "source_name": "LinkedIn", "status": "qualified", "score": 82, "job_title": "CTO", "description": "Budget approved, evaluating vendors. Strong technical fit."},
    {"first_name": "Elena", "last_name": "Volkov", "email": "e.volkov@nordichealth.eu", "phone": "+1-617-555-3011", "company_name": "Nordic Health Group", "industry": "Healthcare", "source_name": "Webinar", "status": "qualified", "score": 78, "job_title": "Chief Digital Officer", "description": "Looking for HIPAA-compliant solution. Demo scheduled."},
    {"first_name": "Derek", "last_name": "Thompson", "email": "d.thompson@silveroak.com", "phone": "+1-214-555-3012", "company_name": "Silver Oak Partners", "industry": "Consulting", "source_name": "Referral", "status": "qualified", "score": 91, "job_title": "Senior VP", "description": "Ready to move forward, finalizing requirements doc."},
    # Unqualified (2)
    {"first_name": "Jessica", "last_name": "Price", "email": "j.price@startup.xyz", "phone": "+1-510-555-3013", "company_name": "Startup XYZ", "industry": "Technology", "source_name": "Website", "status": "unqualified", "score": 15, "job_title": "Intern", "description": "No budget, pre-revenue startup."},
    {"first_name": "Mark", "last_name": "Stevens", "email": "m.stevens@localshop.com", "phone": "+1-916-555-3014", "company_name": "Local Shop", "industry": "Retail", "source_name": "Cold Call", "status": "unqualified", "score": 12, "job_title": "Owner", "description": "Too small for our enterprise product. Referred to SMB solution."},
    # Converted (3)
    {"first_name": "Amanda", "last_name": "Clark", "email": "a.clark@nexgen.com", "phone": "+1-737-555-3015", "company_name": "NexGen Innovations", "industry": "Technology", "source_name": "Trade Show", "status": "converted", "score": 88, "job_title": "VP of Engineering", "description": "Converted to opportunity after successful POC."},
    {"first_name": "William", "last_name": "Zhang", "email": "w.zhang@eastbridge.com", "phone": "+1-415-555-3016", "company_name": "EastBridge Trading", "industry": "Finance", "source_name": "LinkedIn", "status": "converted", "score": 75, "job_title": "Director of Tech", "description": "Converted after 3-month evaluation period."},
    {"first_name": "Grace", "last_name": "Kim", "email": "g.kim@stellarcare.com", "phone": "+1-310-555-3017", "company_name": "Stellar Care Group", "industry": "Healthcare", "source_name": "Referral", "status": "converted", "score": 85, "job_title": "COO", "description": "Converted to contact and opportunity. Large deal potential."},
    # Lost (2)
    {"first_name": "Tyler", "last_name": "Brooks", "email": "t.brooks@fasttrack.io", "phone": "+1-720-555-3018", "company_name": "FastTrack Logistics", "industry": "Logistics", "source_name": "Website", "status": "lost", "score": 35, "job_title": "Operations Manager", "description": "Went with competitor due to pricing."},
    {"first_name": "Nina", "last_name": "Petrova", "email": "n.petrova@eurolink.eu", "phone": "+1-202-555-3019", "company_name": "EuroLink GmbH", "industry": "Manufacturing", "source_name": "Trade Show", "status": "lost", "score": 42, "job_title": "Procurement Lead", "description": "Project cancelled due to budget cuts."},
]


async def _seed_leads(session: AsyncSession, demo_user: User, lead_sources: list[LeadSource]) -> list[Lead]:
    source_map = {s.name: s.id for s in lead_sources}
    leads = []
    for raw in LEADS_DATA:
        data = dict(raw)
        source_name = data.pop("source_name")
        lead = Lead(
            **data,
            source_id=source_map.get(source_name),
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

def _today():
    return date.today()


OPPORTUNITIES_DATA = [
    # Prospecting
    {"name": "Summit Financial Group - CRM Implementation", "amount": 125000, "probability": 10, "stage_name": "Prospecting", "days_to_close": 90, "contact_idx": 5, "company_idx": 2, "description": "Full CRM rollout for wealth management division."},
    {"name": "Meridian Corp - Supply Chain Dashboard", "amount": 85000, "probability": 15, "stage_name": "Prospecting", "days_to_close": 75, "contact_idx": 16, "company_idx": 7, "description": "Custom analytics dashboard for supply chain visibility."},
    # Qualification
    {"name": "Vertex Solutions - Consulting Platform", "amount": 62000, "probability": 25, "stage_name": "Qualification", "days_to_close": 60, "contact_idx": 12, "company_idx": 5, "description": "Client engagement and project management platform."},
    {"name": "Nova Retail - E-commerce Integration", "amount": 38000, "probability": 20, "stage_name": "Qualification", "days_to_close": 45, "contact_idx": 8, "company_idx": 3, "description": "Integrate CRM with Shopify and inventory systems."},
    # Proposal
    {"name": "Acme Technologies - Enterprise License", "amount": 250000, "probability": 45, "stage_name": "Proposal", "days_to_close": 30, "contact_idx": 0, "company_idx": 0, "description": "Enterprise-wide license for 120 users with premium support."},
    {"name": "Cascade Analytics - Data Platform Upgrade", "amount": 48000, "probability": 40, "stage_name": "Proposal", "days_to_close": 35, "contact_idx": 14, "company_idx": 6, "description": "Upgrade to advanced analytics tier with AI features."},
    # Negotiation
    {"name": "Horizon Healthcare - Platform Migration", "amount": 320000, "probability": 65, "stage_name": "Negotiation", "days_to_close": 15, "contact_idx": 3, "company_idx": 1, "description": "Full platform migration from legacy system. 3-year contract."},
    {"name": "Brightpath Education - LMS Integration", "amount": 55000, "probability": 60, "stage_name": "Negotiation", "days_to_close": 20, "contact_idx": 18, "company_idx": 8, "description": "Integrate CRM with their learning management system."},
    # Closed Won (past dates)
    {"name": "Pinnacle Software - Development Tools", "amount": 42000, "probability": 100, "stage_name": "Closed Won", "days_to_close": -15, "contact_idx": 10, "company_idx": 4, "description": "Annual license for development and CI/CD tools."},
    {"name": "Acme Technologies - Training Package", "amount": 18000, "probability": 100, "stage_name": "Closed Won", "days_to_close": -30, "contact_idx": 2, "company_idx": 0, "description": "Staff training program for new platform rollout."},
    # Closed Lost
    {"name": "Meridian Corp - Factory Automation", "amount": 475000, "probability": 0, "stage_name": "Closed Lost", "days_to_close": -10, "contact_idx": 17, "company_idx": 7, "description": "Lost to competitor. Price was primary factor."},
    {"name": "Nova Retail - POS Integration", "amount": 5500, "probability": 0, "stage_name": "Closed Lost", "days_to_close": -25, "contact_idx": 9, "company_idx": 3, "description": "Project deprioritized due to budget constraints."},
]


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

        close_date = today + timedelta(days=days)
        actual_close = close_date if days < 0 else None

        opp = Opportunity(
            **data,
            pipeline_stage_id=stage_map[stage_name],
            expected_close_date=close_date,
            actual_close_date=actual_close,
            currency="USD",
            contact_id=contacts[contact_idx].id,
            company_id=companies[company_idx].id,
            owner_id=demo_user.id,
            created_by_id=demo_user.id,
            loss_reason="Price" if stage_name == "Closed Lost" and "competitor" in data.get("description", "").lower() else ("Budget" if stage_name == "Closed Lost" else None),
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

def _dt(days_offset: int, hour: int = 10) -> datetime:
    """Helper to create a datetime relative to today."""
    return datetime.now(timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days_offset)


ACTIVITIES_DATA = [
    # Calls (10) - past and future
    {"activity_type": "call", "subject": "Discovery call with Sarah Chen", "entity_type": "contacts", "entity_idx": 0, "scheduled_at": _dt(-28, 9), "is_completed": True, "call_duration_minutes": 30, "call_outcome": "connected", "priority": "high", "description": "Initial discovery call to understand Acme's needs."},
    {"activity_type": "call", "subject": "Follow-up call re: proposal", "entity_type": "contacts", "entity_idx": 5, "scheduled_at": _dt(-21, 14), "is_completed": True, "call_duration_minutes": 45, "call_outcome": "connected", "priority": "high", "description": "Discussed proposal details with James Thornton."},
    {"activity_type": "call", "subject": "Cold call - DataDriven AI", "entity_type": "leads", "entity_idx": 5, "scheduled_at": _dt(-14, 11), "is_completed": True, "call_duration_minutes": 15, "call_outcome": "voicemail", "priority": "normal", "description": "Left voicemail for Sophie Anderson."},
    {"activity_type": "call", "subject": "Pricing discussion with Horizon HC", "entity_type": "contacts", "entity_idx": 3, "scheduled_at": _dt(-10, 15), "is_completed": True, "call_duration_minutes": 60, "call_outcome": "connected", "priority": "urgent", "description": "Detailed pricing review for platform migration."},
    {"activity_type": "call", "subject": "Check-in with Pinnacle Software", "entity_type": "contacts", "entity_idx": 10, "scheduled_at": _dt(-5, 10), "is_completed": True, "call_duration_minutes": 20, "call_outcome": "connected", "priority": "normal", "description": "Post-sale check-in call. Customer very satisfied."},
    {"activity_type": "call", "subject": "Qualification call - LogicGate", "entity_type": "leads", "entity_idx": 9, "scheduled_at": _dt(-3, 13), "is_completed": True, "call_duration_minutes": 35, "call_outcome": "connected", "priority": "high", "description": "Budget confirmed at $80k. Decision timeline: Q1."},
    {"activity_type": "call", "subject": "Technical review with Cascade", "entity_type": "contacts", "entity_idx": 14, "scheduled_at": _dt(1, 10), "is_completed": False, "call_duration_minutes": None, "call_outcome": None, "priority": "normal", "description": "Review API integration requirements."},
    {"activity_type": "call", "subject": "Negotiation call - Brightpath", "entity_type": "contacts", "entity_idx": 18, "scheduled_at": _dt(3, 14), "is_completed": False, "call_duration_minutes": None, "call_outcome": None, "priority": "high", "description": "Finalize contract terms for LMS integration."},
    {"activity_type": "call", "subject": "Follow up on trade show leads", "entity_type": "leads", "entity_idx": 2, "scheduled_at": _dt(5, 11), "is_completed": False, "call_duration_minutes": None, "call_outcome": None, "priority": "normal", "description": "Follow up with Ahmad Hassan from FinTech Summit."},
    {"activity_type": "call", "subject": "Quarterly review - Acme Technologies", "entity_type": "contacts", "entity_idx": 0, "scheduled_at": _dt(10, 15), "is_completed": False, "call_duration_minutes": None, "call_outcome": None, "priority": "normal", "description": "Quarterly business review with Sarah Chen."},
    # Emails (10)
    {"activity_type": "email", "subject": "Sent proposal to Summit Financial", "entity_type": "contacts", "entity_idx": 5, "scheduled_at": _dt(-25, 9), "is_completed": True, "email_to": "j.thornton@summitfg.com", "email_opened": True, "priority": "high", "description": "Comprehensive CRM implementation proposal attached."},
    {"activity_type": "email", "subject": "Product brochure to Nova Retail", "entity_type": "contacts", "entity_idx": 8, "scheduled_at": _dt(-20, 10), "is_completed": True, "email_to": "priya@novaretail.co", "email_opened": True, "priority": "normal", "description": "Sent product overview and case studies."},
    {"activity_type": "email", "subject": "Technical specs to Meridian Corp", "entity_type": "contacts", "entity_idx": 17, "scheduled_at": _dt(-18, 11), "is_completed": True, "email_to": "c.moore@meridiancorp.com", "email_opened": False, "priority": "normal", "description": "Integration specs for factory automation system."},
    {"activity_type": "email", "subject": "Contract draft to Horizon Healthcare", "entity_type": "contacts", "entity_idx": 3, "scheduled_at": _dt(-8, 9), "is_completed": True, "email_to": "r.williams@horizonhc.com", "email_opened": True, "priority": "urgent", "description": "3-year contract draft for review by legal team."},
    {"activity_type": "email", "subject": "Thank you - Pinnacle deal closed", "entity_type": "contacts", "entity_idx": 10, "scheduled_at": _dt(-15, 16), "is_completed": True, "email_to": "tom@pinnaclesoft.com", "email_opened": True, "priority": "normal", "description": "Thank you email with onboarding timeline."},
    {"activity_type": "email", "subject": "Send pricing sheet to CloudSync", "entity_type": "leads", "entity_idx": 3, "scheduled_at": _dt(-2, 10), "is_completed": True, "email_to": "l.bennett@cloudsync.com", "email_opened": False, "priority": "normal", "description": "Standard pricing sheet with enterprise discount tier."},
    {"activity_type": "email", "subject": "Case study for Nordic Health", "entity_type": "leads", "entity_idx": 10, "scheduled_at": _dt(-1, 14), "is_completed": True, "email_to": "e.volkov@nordichealth.eu", "email_opened": True, "priority": "high", "description": "Healthcare-specific case study showing 40% efficiency gain."},
    {"activity_type": "email", "subject": "Follow-up: Vertex Solutions demo", "entity_type": "contacts", "entity_idx": 12, "scheduled_at": _dt(1, 9), "is_completed": False, "email_to": "k.obrien@vertexsol.com", "priority": "normal", "description": "Send demo recording and next steps."},
    {"activity_type": "email", "subject": "ROI analysis for Acme enterprise deal", "entity_type": "contacts", "entity_idx": 0, "scheduled_at": _dt(2, 10), "is_completed": False, "email_to": "sarah.chen@acmetech.io", "priority": "high", "description": "Custom ROI analysis based on their current spend."},
    {"activity_type": "email", "subject": "Renewal reminder - Cascade Analytics", "entity_type": "contacts", "entity_idx": 14, "scheduled_at": _dt(7, 9), "is_completed": False, "email_to": "alex@cascadeanalytics.io", "priority": "normal", "description": "License renewal coming up in 60 days."},
    # Meetings (8)
    {"activity_type": "meeting", "subject": "Product demo - Acme Technologies", "entity_type": "contacts", "entity_idx": 1, "scheduled_at": _dt(-22, 14), "is_completed": True, "meeting_location": "Zoom", "priority": "high", "description": "Live product demo for CTO Marcus Johnson and his team."},
    {"activity_type": "meeting", "subject": "On-site visit - Horizon Healthcare", "entity_type": "contacts", "entity_idx": 3, "scheduled_at": _dt(-12, 10), "is_completed": True, "meeting_location": "200 Beacon Street, Boston, MA", "priority": "urgent", "description": "On-site requirements gathering session with medical and IT teams."},
    {"activity_type": "meeting", "subject": "Lunch with Kevin O'Brien", "entity_type": "contacts", "entity_idx": 12, "scheduled_at": _dt(-7, 12), "is_completed": True, "meeting_location": "The Capital Grille, Atlanta", "priority": "normal", "description": "Relationship-building lunch. Discussed potential partnership."},
    {"activity_type": "meeting", "subject": "Security review - Summit Financial", "entity_type": "contacts", "entity_idx": 6, "scheduled_at": _dt(-4, 15), "is_completed": True, "meeting_location": "Microsoft Teams", "priority": "high", "description": "Security and compliance review with their IT team."},
    {"activity_type": "meeting", "subject": "POC kickoff - Vertex Solutions", "entity_type": "contacts", "entity_idx": 13, "scheduled_at": _dt(2, 10), "is_completed": False, "meeting_location": "Google Meet", "priority": "high", "description": "Kick off 2-week proof of concept with Diana Foster's team."},
    {"activity_type": "meeting", "subject": "Board presentation - Meridian Corp", "entity_type": "contacts", "entity_idx": 16, "scheduled_at": _dt(5, 9), "is_completed": False, "meeting_location": "2500 Woodward Avenue, Detroit, MI", "priority": "urgent", "description": "Present to board of directors for final approval."},
    {"activity_type": "meeting", "subject": "Team strategy session", "entity_type": "contacts", "entity_idx": 0, "scheduled_at": _dt(8, 14), "is_completed": False, "meeting_location": "Internal - Conference Room A", "priority": "normal", "description": "Q2 pipeline review and strategy planning."},
    {"activity_type": "meeting", "subject": "Annual review - Brightpath Education", "entity_type": "contacts", "entity_idx": 19, "scheduled_at": _dt(12, 10), "is_completed": False, "meeting_location": "Zoom", "priority": "normal", "description": "Annual partnership review with Olivia Taylor."},
    # Tasks (7)
    {"activity_type": "task", "subject": "Prepare Acme enterprise proposal", "entity_type": "opportunities", "entity_idx": 4, "scheduled_at": _dt(-6, 9), "due_date": (_today() + timedelta(days=-4)), "is_completed": True, "priority": "urgent", "description": "Finalize 120-user enterprise license proposal with pricing."},
    {"activity_type": "task", "subject": "Update CRM with trade show leads", "entity_type": "leads", "entity_idx": 2, "scheduled_at": _dt(-2, 9), "due_date": _today(), "is_completed": True, "priority": "normal", "description": "Enter all leads from FinTech Summit into the system."},
    {"activity_type": "task", "subject": "Create demo environment for Horizon", "entity_type": "opportunities", "entity_idx": 6, "scheduled_at": _dt(0, 9), "due_date": (_today() + timedelta(days=3)), "is_completed": False, "priority": "high", "description": "Set up sandbox environment with sample healthcare data."},
    {"activity_type": "task", "subject": "Send contract to legal team", "entity_type": "opportunities", "entity_idx": 7, "scheduled_at": _dt(1, 9), "due_date": (_today() + timedelta(days=2)), "is_completed": False, "priority": "high", "description": "Forward Brightpath contract to internal legal for review."},
    {"activity_type": "task", "subject": "Research competitor pricing", "entity_type": "leads", "entity_idx": 9, "scheduled_at": _dt(2, 9), "due_date": (_today() + timedelta(days=5)), "is_completed": False, "priority": "normal", "description": "Compile competitor pricing comparison for LogicGate evaluation."},
    {"activity_type": "task", "subject": "Schedule QBR with all customers", "entity_type": "contacts", "entity_idx": 0, "scheduled_at": _dt(3, 9), "due_date": (_today() + timedelta(days=7)), "is_completed": False, "priority": "normal", "description": "Reach out to all active customers to schedule quarterly reviews."},
    {"activity_type": "task", "subject": "Follow up on lost deals", "entity_type": "opportunities", "entity_idx": 10, "scheduled_at": _dt(4, 9), "due_date": (_today() + timedelta(days=10)), "is_completed": False, "priority": "low", "description": "Send check-in to Meridian and Nova 30 days after losing deals."},
]


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

CAMPAIGNS_DATA = [
    {
        "name": "Q1 Product Launch",
        "description": "Major product launch campaign targeting enterprise tech companies. Multi-channel approach across email, LinkedIn, and webinars.",
        "campaign_type": "email",
        "status": "completed",
        "start_date": _today() - timedelta(days=60),
        "end_date": _today() - timedelta(days=15),
        "budget_amount": 15000,
        "actual_cost": 13200,
        "expected_revenue": 200000,
        "actual_revenue": 178000,
        "num_sent": 2500,
        "num_responses": 340,
        "num_converted": 28,
    },
    {
        "name": "Spring Webinar Series",
        "description": "Three-part webinar series on digital transformation. Topics: Cloud Migration, AI in Business, Data-Driven Decisions.",
        "campaign_type": "webinar",
        "status": "active",
        "start_date": _today() - timedelta(days=20),
        "end_date": _today() + timedelta(days=40),
        "budget_amount": 8000,
        "actual_cost": 3500,
        "expected_revenue": 120000,
        "actual_revenue": 45000,
        "num_sent": 5000,
        "num_responses": 620,
        "num_converted": 12,
    },
    {
        "name": "Customer Reactivation",
        "description": "Re-engagement campaign targeting churned and inactive accounts from the past 6 months. Special pricing offers included.",
        "campaign_type": "email",
        "status": "active",
        "start_date": _today() - timedelta(days=10),
        "end_date": _today() + timedelta(days=50),
        "budget_amount": 5000,
        "actual_cost": 1200,
        "expected_revenue": 75000,
        "actual_revenue": 8000,
        "num_sent": 800,
        "num_responses": 95,
        "num_converted": 4,
    },
    {
        "name": "Holiday Promo 2026",
        "description": "End-of-year promotional campaign with special discounts for new annual subscriptions. Early bird pricing for Q1 signups.",
        "campaign_type": "email",
        "status": "planned",
        "start_date": _today() + timedelta(days=90),
        "end_date": _today() + timedelta(days=120),
        "budget_amount": 20000,
        "actual_cost": 0,
        "expected_revenue": 300000,
        "actual_revenue": 0,
        "num_sent": 0,
        "num_responses": 0,
        "num_converted": 0,
    },
]


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

NOTES_DATA = [
    {"entity_type": "contact", "entity_idx": 0, "list_key": "contacts", "content": "Sarah is very responsive and prefers email communication. Key decision maker for all software purchases at Acme. Has been with the company for 8 years and knows the tech stack inside out."},
    {"entity_type": "contact", "entity_idx": 3, "list_key": "contacts", "content": "Dr. Williams needs HIPAA compliance documentation before moving forward. His team requires a dedicated implementation manager. Budget approval expected by end of month."},
    {"entity_type": "contact", "entity_idx": 5, "list_key": "contacts", "content": "James mentioned they are also evaluating Salesforce and HubSpot. Main differentiator for us is custom reporting capabilities. He values ROI metrics heavily."},
    {"entity_type": "lead", "entity_idx": 9, "list_key": "leads", "content": "Chris Walker at LogicGate has confirmed $80k budget allocated for CRM implementation. Timeline: decision by end of Q1, go-live by Q2. Strong champion internally."},
    {"entity_type": "lead", "entity_idx": 10, "list_key": "leads", "content": "Elena needs GDPR compliance as well since Nordic Health operates in EU. Her team of 15 will be the initial users with plans to expand to 50+ by year end."},
    {"entity_type": "opportunity", "entity_idx": 4, "list_key": "opportunities", "content": "Acme enterprise deal update: Sarah confirmed the 120-user count. They want premium support included. Possible upsell for custom integrations worth additional $50k."},
    {"entity_type": "opportunity", "entity_idx": 6, "list_key": "opportunities", "content": "Horizon Healthcare platform migration is the largest deal in pipeline. Legal review in progress. Dr. Williams is pushing for Q1 completion. Risk: their IT team is understaffed for migration."},
    {"entity_type": "opportunity", "entity_idx": 8, "list_key": "opportunities", "content": "Pinnacle deal closed smoothly. Tom was very pleased with the onboarding process. Good reference customer for future deals. They may refer us to 2-3 other Portland tech companies."},
    {"entity_type": "company", "entity_idx": 0, "list_key": "companies", "content": "Acme Technologies is our highest-value prospect. They use Jira, Slack, and AWS. Integration with these tools will be important. Annual tech budget is approximately $2M."},
    {"entity_type": "company", "entity_idx": 1, "list_key": "companies", "content": "Horizon Healthcare is undergoing a major digital transformation initiative. The CEO has mandated all departments upgrade their systems by 2027. Budget is not a constraint."},
    {"entity_type": "company", "entity_idx": 2, "list_key": "companies", "content": "Summit Financial has strict security requirements. SOC 2 Type II certification is mandatory. They also require data residency in the US with no offshore data processing."},
    {"entity_type": "lead", "entity_idx": 11, "list_key": "leads", "content": "Derek Thompson at Silver Oak Partners is very close to signing. He has brought in their legal team to review the contract. Expected to close within 2 weeks."},
    {"entity_type": "contact", "entity_idx": 12, "list_key": "contacts", "content": "Kevin O'Brien is interested in a strategic partnership where Vertex Solutions resells our product to their consulting clients. Could be a significant channel opportunity."},
    {"entity_type": "opportunity", "entity_idx": 10, "list_key": "opportunities", "content": "Post-mortem on Meridian loss: they went with a competitor who offered 30% lower pricing. Lesson learned - need to better articulate our value proposition for manufacturing vertical."},
]


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

TAGS_DATA = [
    {"name": "hot-lead", "color": "#ef4444"},
    {"name": "enterprise", "color": "#8b5cf6"},
    {"name": "startup", "color": "#06b6d4"},
    {"name": "needs-follow-up", "color": "#f59e0b"},
    {"name": "decision-maker", "color": "#22c55e"},
    {"name": "technical-buyer", "color": "#3b82f6"},
    {"name": "budget-approved", "color": "#10b981"},
    {"name": "competitor-risk", "color": "#f97316"},
    {"name": "upsell-opportunity", "color": "#a855f7"},
    {"name": "referral", "color": "#14b8a6"},
]


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

ENTITY_TAG_ASSIGNMENTS = [
    # hot-lead (idx 0) applied to qualified leads
    {"tag_idx": 0, "entity_type": "lead", "list_key": "leads", "entity_idx": 9},   # Chris Walker
    {"tag_idx": 0, "entity_type": "lead", "list_key": "leads", "entity_idx": 11},  # Derek Thompson
    # enterprise (idx 1) applied to large companies
    {"tag_idx": 1, "entity_type": "company", "list_key": "companies", "entity_idx": 1},  # Horizon Healthcare
    {"tag_idx": 1, "entity_type": "company", "list_key": "companies", "entity_idx": 2},  # Summit Financial
    {"tag_idx": 1, "entity_type": "company", "list_key": "companies", "entity_idx": 7},  # Meridian Corp
    {"tag_idx": 1, "entity_type": "opportunity", "list_key": "opportunities", "entity_idx": 4},  # Acme Enterprise License
    # startup (idx 2)
    {"tag_idx": 2, "entity_type": "company", "list_key": "companies", "entity_idx": 4},  # Pinnacle Software
    {"tag_idx": 2, "entity_type": "company", "list_key": "companies", "entity_idx": 6},  # Cascade Analytics
    # needs-follow-up (idx 3)
    {"tag_idx": 3, "entity_type": "lead", "list_key": "leads", "entity_idx": 0},   # Ryan Mitchell
    {"tag_idx": 3, "entity_type": "lead", "list_key": "leads", "entity_idx": 5},   # Sophie Anderson
    {"tag_idx": 3, "entity_type": "contact", "list_key": "contacts", "entity_idx": 12},  # Kevin O'Brien
    # decision-maker (idx 4)
    {"tag_idx": 4, "entity_type": "contact", "list_key": "contacts", "entity_idx": 0},  # Sarah Chen
    {"tag_idx": 4, "entity_type": "contact", "list_key": "contacts", "entity_idx": 3},  # Dr. Robert Williams
    {"tag_idx": 4, "entity_type": "contact", "list_key": "contacts", "entity_idx": 5},  # James Thornton
    {"tag_idx": 4, "entity_type": "contact", "list_key": "contacts", "entity_idx": 8},  # Priya Sharma
    # technical-buyer (idx 5)
    {"tag_idx": 5, "entity_type": "contact", "list_key": "contacts", "entity_idx": 1},  # Marcus Johnson (CTO)
    {"tag_idx": 5, "entity_type": "contact", "list_key": "contacts", "entity_idx": 6},  # Emily Davis
    {"tag_idx": 5, "entity_type": "contact", "list_key": "contacts", "entity_idx": 18},  # Nathan Wright (CTO)
    # budget-approved (idx 6)
    {"tag_idx": 6, "entity_type": "lead", "list_key": "leads", "entity_idx": 9},   # Chris Walker
    {"tag_idx": 6, "entity_type": "opportunity", "list_key": "opportunities", "entity_idx": 6},  # Horizon migration
    # competitor-risk (idx 7)
    {"tag_idx": 7, "entity_type": "opportunity", "list_key": "opportunities", "entity_idx": 0},  # Summit Financial
    {"tag_idx": 7, "entity_type": "contact", "list_key": "contacts", "entity_idx": 5},  # James Thornton
    # upsell-opportunity (idx 8)
    {"tag_idx": 8, "entity_type": "opportunity", "list_key": "opportunities", "entity_idx": 4},  # Acme enterprise
    {"tag_idx": 8, "entity_type": "contact", "list_key": "contacts", "entity_idx": 10},  # Tom Bradley
    {"tag_idx": 8, "entity_type": "company", "list_key": "companies", "entity_idx": 8},  # Brightpath
    # referral (idx 9)
    {"tag_idx": 9, "entity_type": "lead", "list_key": "leads", "entity_idx": 4},   # Carlos Reyes
    {"tag_idx": 9, "entity_type": "lead", "list_key": "leads", "entity_idx": 11},  # Derek Thompson
    {"tag_idx": 9, "entity_type": "lead", "list_key": "leads", "entity_idx": 16},  # Grace Kim
]


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

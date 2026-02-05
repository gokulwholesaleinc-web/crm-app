#!/usr/bin/env python3
"""
Database seeding script with realistic generated data.
Uses Faker for generating realistic test data - NO hardcoded values.

Usage:
    python scripts/seed_data.py

Or from Docker:
    docker exec crm_backend python scripts/seed_data.py
"""

import asyncio
import random
from datetime import datetime, timedelta
from faker import Faker
from passlib.context import CryptContext

# Initialize Faker
fake = Faker()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


async def seed_database():
    """Seed the database with realistic test data."""
    # Import here to ensure proper path resolution
    import sys
    sys.path.insert(0, '/app')

    from sqlalchemy import select, text
    from src.database import async_session_maker, engine, Base

    # Import all models
    from src.auth.models import User
    from src.contacts.models import Contact
    from src.companies.models import Company
    from src.leads.models import Lead, LeadSource
    from src.opportunities.models import Opportunity, PipelineStage
    from src.activities.models import Activity
    from src.campaigns.models import Campaign, CampaignMember
    from src.core.models import Tag, Note

    print("Starting database seeding...")

    async with async_session_maker() as session:
        # Check if contacts exist (more specific check)
        result = await session.execute(select(Contact).limit(1))
        if result.scalar_one_or_none():
            print("Database already has seed data. Skipping.")
            return

        # Get existing users or create new ones
        result = await session.execute(select(User))
        existing_users = result.scalars().all()
        users = list(existing_users) if existing_users else []
        print(f"Found {len(users)} existing users")

        # ============================================================
        # 1. Create Tags
        # ============================================================
        print("Creating tags...")
        tag_names = ["VIP", "Hot Lead", "Enterprise", "SMB", "Partner", "Referral", "New", "Follow-up"]
        tag_colors = ["#EF4444", "#F59E0B", "#10B981", "#3B82F6", "#8B5CF6", "#EC4899", "#6366F1", "#14B8A6"]
        tags = []
        for name, color in zip(tag_names, tag_colors):
            tag = Tag(name=name, color=color)
            session.add(tag)
            tags.append(tag)
        await session.flush()
        print(f"  Created {len(tags)} tags")

        # ============================================================
        # 2. Create Users (if none exist)
        # ============================================================
        if not users:
            print("Creating users...")

            # Create main test user with known credentials
            test_user = User(
                email="demo@example.com",
                hashed_password=get_password_hash("demo123"),
                full_name=fake.name(),
                phone=fake.phone_number()[:20],
                job_title="Sales Manager",
                is_active=True,
                is_superuser=True,
            )
            session.add(test_user)
            users.append(test_user)

            # Create secondary test user
            test_user2 = User(
                email="test@test.com",
                hashed_password=get_password_hash("test1"),
                full_name=fake.name(),
                phone=fake.phone_number()[:20],
                job_title="Sales Representative",
                is_active=True,
                is_superuser=False,
            )
            session.add(test_user2)
            users.append(test_user2)

            # Create additional sales team members
            job_titles = ["Sales Representative", "Account Executive", "Business Development", "Sales Director", "Account Manager"]
            for i in range(4):
                user = User(
                    email=fake.unique.email(),
                    hashed_password=get_password_hash(fake.password()),
                    full_name=fake.name(),
                    phone=fake.phone_number()[:20],
                    job_title=random.choice(job_titles),
                    is_active=True,
                    is_superuser=False,
                )
                session.add(user)
                users.append(user)
            await session.flush()
            print(f"  Created {len(users)} users")
        else:
            print(f"  Using {len(users)} existing users")

        # ============================================================
        # 3. Create Lead Sources
        # ============================================================
        print("Creating lead sources...")
        source_names = ["Website", "LinkedIn", "Referral", "Trade Show", "Cold Call", "Email Campaign", "Google Ads", "Partner"]
        lead_sources = []
        for name in source_names:
            source = LeadSource(
                name=name,
                description=f"Leads from {name.lower()}",
                is_active=True,
            )
            session.add(source)
            lead_sources.append(source)
        await session.flush()
        print(f"  Created {len(lead_sources)} lead sources")

        # ============================================================
        # 4. Create Pipeline Stages
        # ============================================================
        print("Creating pipeline stages...")
        stage_data = [
            ("Qualification", 10, "#6366F1"),
            ("Discovery", 25, "#8B5CF6"),
            ("Proposal", 50, "#F59E0B"),
            ("Negotiation", 75, "#10B981"),
            ("Closed Won", 100, "#22C55E"),
            ("Closed Lost", 0, "#EF4444"),
        ]
        pipeline_stages = []
        for order, (name, probability, color) in enumerate(stage_data):
            stage = PipelineStage(
                name=name,
                probability=probability,
                order=order,
                color=color,
                is_active=True,
            )
            session.add(stage)
            pipeline_stages.append(stage)
        await session.flush()
        print(f"  Created {len(pipeline_stages)} pipeline stages")

        # ============================================================
        # 5. Create Companies
        # ============================================================
        print("Creating companies...")
        companies = []
        industries = ["Technology", "Healthcare", "Finance", "Manufacturing", "Retail", "Education", "Real Estate", "Consulting"]
        company_sizes = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"]

        for _ in range(20):
            company = Company(
                name=fake.company(),
                website=fake.url(),
                industry=random.choice(industries),
                company_size=random.choice(company_sizes),
                address_line1=fake.street_address(),
                city=fake.city(),
                state=fake.state_abbr(),
                country=fake.country_code(),
                postal_code=fake.postcode(),
                phone=fake.phone_number()[:20],
                description=fake.catch_phrase(),
                owner_id=random.choice(users).id,
            )
            session.add(company)
            companies.append(company)
        await session.flush()
        print(f"  Created {len(companies)} companies")

        # ============================================================
        # 6. Create Contacts
        # ============================================================
        print("Creating contacts...")
        contacts = []

        for _ in range(50):
            contact = Contact(
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                email=fake.unique.email(),
                phone=fake.phone_number()[:20],
                mobile=fake.phone_number()[:20],
                job_title=fake.job(),
                department=random.choice(["Sales", "Marketing", "Engineering", "Finance", "HR", "Operations"]),
                company_id=random.choice(companies).id if random.random() > 0.2 else None,
                address_line1=fake.street_address(),
                city=fake.city(),
                state=fake.state_abbr(),
                country=fake.country_code(),
                postal_code=fake.postcode(),
                linkedin_url=f"https://linkedin.com/in/{fake.user_name()}",
                description=fake.paragraph() if random.random() > 0.5 else None,
                owner_id=random.choice(users).id,
            )
            session.add(contact)
            contacts.append(contact)
        await session.flush()
        print(f"  Created {len(contacts)} contacts")

        # ============================================================
        # 7. Create Leads
        # ============================================================
        print("Creating leads...")
        leads = []
        lead_statuses = ["new", "contacted", "qualified", "unqualified"]

        for _ in range(30):
            lead = Lead(
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                email=fake.unique.email(),
                phone=fake.phone_number()[:20],
                company_name=fake.company(),
                job_title=fake.job(),
                source_id=random.choice(lead_sources).id,
                status=random.choice(lead_statuses),
                score=random.randint(0, 100),
                description=fake.paragraph() if random.random() > 0.5 else None,
                owner_id=random.choice(users).id,
            )
            session.add(lead)
            leads.append(lead)
        await session.flush()
        print(f"  Created {len(leads)} leads")

        # ============================================================
        # 8. Create Opportunities
        # ============================================================
        print("Creating opportunities...")
        opportunities = []

        # Only use active stages (not Closed Won/Lost for most)
        active_stages = pipeline_stages[:4]  # Qualification through Negotiation
        all_stages = pipeline_stages

        for _ in range(25):
            is_closed = random.random() > 0.7
            stage = random.choice(all_stages) if is_closed else random.choice(active_stages)
            close_date = fake.date_between(start_date="-30d", end_date="+90d")

            opportunity = Opportunity(
                name=f"{fake.company()} - {fake.bs().title()}",
                amount=random.randint(5000, 500000),
                pipeline_stage_id=stage.id,
                contact_id=random.choice(contacts).id if random.random() > 0.3 else None,
                company_id=random.choice(companies).id if random.random() > 0.2 else None,
                expected_close_date=close_date,
                probability=stage.probability,
                description=fake.paragraph(),
                owner_id=random.choice(users).id,
            )
            session.add(opportunity)
            opportunities.append(opportunity)
        await session.flush()
        print(f"  Created {len(opportunities)} opportunities")

        # ============================================================
        # 9. Create Activities
        # ============================================================
        print("Creating activities...")
        activities = []
        activity_types = ["call", "email", "meeting", "task", "note"]

        # Create activities for contacts
        for contact in random.sample(contacts, min(30, len(contacts))):
            for _ in range(random.randint(1, 5)):
                activity_type = random.choice(activity_types)
                is_completed = random.random() > 0.4
                scheduled_at = fake.date_time_between(start_date="-30d", end_date="+14d")

                activity = Activity(
                    activity_type=activity_type,
                    subject=f"{activity_type.title()}: {fake.sentence(nb_words=4)}",
                    description=fake.paragraph() if random.random() > 0.3 else None,
                    entity_type="contact",
                    entity_id=contact.id,
                    scheduled_at=scheduled_at,
                    completed_at=scheduled_at if is_completed else None,
                    due_date=scheduled_at.date() if activity_type == "task" else None,
                    call_duration_minutes=random.choice([15, 30, 45, 60, 90]) if activity_type == "call" else None,
                    owner_id=random.choice(users).id,
                    assigned_to_id=random.choice(users).id,
                )
                session.add(activity)
                activities.append(activity)

        # Create activities for opportunities
        for opp in random.sample(opportunities, min(15, len(opportunities))):
            for _ in range(random.randint(1, 3)):
                activity_type = random.choice(activity_types)
                is_completed = random.random() > 0.5
                scheduled_at = fake.date_time_between(start_date="-14d", end_date="+14d")

                activity = Activity(
                    activity_type=activity_type,
                    subject=f"{activity_type.title()}: {fake.sentence(nb_words=4)}",
                    description=fake.paragraph() if random.random() > 0.3 else None,
                    entity_type="opportunity",
                    entity_id=opp.id,
                    scheduled_at=scheduled_at,
                    completed_at=scheduled_at if is_completed else None,
                    due_date=scheduled_at.date() if activity_type == "task" else None,
                    call_duration_minutes=random.choice([15, 30, 45, 60]) if activity_type == "call" else None,
                    owner_id=random.choice(users).id,
                    assigned_to_id=random.choice(users).id,
                )
                session.add(activity)
                activities.append(activity)

        await session.flush()
        print(f"  Created {len(activities)} activities")

        # ============================================================
        # 10. Create Campaigns
        # ============================================================
        print("Creating campaigns...")
        campaigns = []
        campaign_types = ["Email", "Social Media", "Webinar", "Trade Show", "Content", "PPC"]
        campaign_statuses = ["draft", "active", "paused", "completed"]

        for _ in range(8):
            start_date = fake.date_between(start_date="-60d", end_date="+30d")
            end_date = start_date + timedelta(days=random.randint(14, 90))

            campaign = Campaign(
                name=f"{fake.catch_phrase()} Campaign",
                description=fake.paragraph(),
                campaign_type=random.choice(campaign_types),
                status=random.choice(campaign_statuses),
                start_date=start_date,
                end_date=end_date,
                budget_amount=random.randint(1000, 50000),
                expected_revenue=random.randint(5000, 200000),
                actual_revenue=random.randint(0, 150000) if random.random() > 0.5 else None,
                owner_id=random.choice(users).id,
            )
            session.add(campaign)
            campaigns.append(campaign)
        await session.flush()

        # Add campaign members
        for campaign in campaigns:
            # Add some contacts as members
            member_contacts = random.sample(contacts, min(random.randint(5, 15), len(contacts)))
            for contact in member_contacts:
                member = CampaignMember(
                    campaign_id=campaign.id,
                    member_type="contact",
                    member_id=contact.id,
                    status=random.choice(["pending", "sent", "opened", "clicked", "converted"]),
                    responded_at=fake.date_time_between(start_date="-30d", end_date="now") if random.random() > 0.5 else None,
                )
                session.add(member)

            # Add some leads as members
            member_leads = random.sample(leads, min(random.randint(3, 10), len(leads)))
            for lead in member_leads:
                member = CampaignMember(
                    campaign_id=campaign.id,
                    member_type="lead",
                    member_id=lead.id,
                    status=random.choice(["pending", "sent", "opened", "clicked"]),
                    responded_at=fake.date_time_between(start_date="-30d", end_date="now") if random.random() > 0.5 else None,
                )
                session.add(member)

        await session.flush()
        print(f"  Created {len(campaigns)} campaigns with members")

        # ============================================================
        # 11. Create Notes
        # ============================================================
        print("Creating notes...")
        note_count = 0

        # Notes for contacts
        for contact in random.sample(contacts, min(20, len(contacts))):
            for _ in range(random.randint(1, 3)):
                note = Note(
                    content=fake.paragraph(nb_sentences=random.randint(1, 4)),
                    entity_type="contact",
                    entity_id=contact.id,
                    created_by_id=random.choice(users).id,
                )
                session.add(note)
                note_count += 1

        # Notes for opportunities
        for opp in random.sample(opportunities, min(15, len(opportunities))):
            for _ in range(random.randint(1, 2)):
                note = Note(
                    content=fake.paragraph(nb_sentences=random.randint(1, 4)),
                    entity_type="opportunity",
                    entity_id=opp.id,
                    created_by_id=random.choice(users).id,
                )
                session.add(note)
                note_count += 1

        await session.flush()
        print(f"  Created {note_count} notes")

        # ============================================================
        # Commit all changes
        # ============================================================
        await session.commit()

        print("\n" + "=" * 50)
        print("Database seeding complete!")
        print("=" * 50)
        print(f"\nSummary:")
        print(f"  - Users: {len(users)}")
        print(f"  - Tags: {len(tags)}")
        print(f"  - Lead Sources: {len(lead_sources)}")
        print(f"  - Pipeline Stages: {len(pipeline_stages)}")
        print(f"  - Companies: {len(companies)}")
        print(f"  - Contacts: {len(contacts)}")
        print(f"  - Leads: {len(leads)}")
        print(f"  - Opportunities: {len(opportunities)}")
        print(f"  - Activities: {len(activities)}")
        print(f"  - Campaigns: {len(campaigns)}")
        print(f"  - Notes: {note_count}")
        print(f"\nLogin credentials:")
        print(f"  1. Email: demo@example.com  |  Password: demo123  (Admin)")
        print(f"  2. Email: test@test.com     |  Password: test1    (User)")


if __name__ == "__main__":
    asyncio.run(seed_database())

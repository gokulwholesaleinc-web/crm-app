"""FastAPI CRM Application - Main Entry Point."""

import os
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.config import settings
from src.database import engine, init_db
from src.core.router_utils import CurrentUser
from src.core.rate_limit import limiter
from src.whitelabel.middleware import TenantMiddleware

# Import routers
from src.auth.router import router as auth_router
from src.contacts.router import router as contacts_router
from src.companies.router import router as companies_router
from src.leads.router import router as leads_router
from src.opportunities.router import router as opportunities_router
from src.activities.router import router as activities_router
from src.campaigns.router import router as campaigns_router
from src.dashboard.router import router as dashboard_router
from src.whitelabel.router import router as whitelabel_router
from src.import_export.router import router as import_export_router
from src.notes.router import router as notes_router
from src.workflows.router import router as workflows_router
from src.attachments.router import router as attachments_router
from src.dedup.router import router as dedup_router
from src.email.router import router as email_router
from src.notifications.router import router as notifications_router
from src.filters.router import router as filters_router
from src.reports.router import router as reports_router
from src.audit.router import router as audit_router
from src.comments.router import router as comments_router
from src.roles.router import router as roles_router
from src.webhooks.router import router as webhooks_router
from src.assignment.router import router as assignment_router
from src.sequences.router import router as sequences_router
from src.core.sharing_router import router as sharing_router
from src.quotes.router import router as quotes_router
from src.payments.router import router as payments_router
from src.proposals.router import router as proposals_router
from src.contracts.router import router as contracts_router
from src.admin.router import router as admin_router
from src.ai.router import router as ai_router
from src.meta.router import router as meta_router
from src.expenses.router import router as expenses_router
from src.integrations.google_calendar.router import router as google_calendar_router
from src.settings.router import router as settings_router


async def _run_production_migrations():
    """Run idempotent schema migrations using raw asyncpg (no ORM)."""
    import asyncpg

    admin_emails = [
        e.strip() for e in os.getenv("ADMIN_EMAILS", "admin@admin.com").split(",") if e.strip()
    ]

    db_url = settings.db_url
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    if "?sslmode=" in db_url:
        db_url = db_url.split("?")[0]

    try:
        conn = await asyncpg.connect(db_url)
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'sales_rep' NOT NULL")
            placeholders = ", ".join(f"${i+1}" for i in range(len(admin_emails)))
            await conn.execute(f"""
                UPDATE users SET role = 'admin', is_superuser = true
                WHERE email IN ({placeholders})
                AND (role != 'admin' OR is_superuser = false)
            """, *admin_emails)
            await conn.execute(f"""
                INSERT INTO user_roles (user_id, role_id, created_at, updated_at)
                SELECT u.id, r.id, NOW(), NOW()
                FROM users u, roles r
                WHERE u.email IN ({placeholders})
                AND r.name = 'admin'
                AND NOT EXISTS (
                    SELECT 1 FROM user_roles ur WHERE ur.user_id = u.id AND ur.role_id = r.id
                )
            """, *admin_emails)

            # Unique constraints and missing indexes
            for idx_sql in [
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_contacts_unique_email ON contacts(email) WHERE email IS NOT NULL",
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_companies_unique_name_owner ON companies(name, owner_id)",
                "CREATE INDEX IF NOT EXISTS ix_companies_status ON companies(status)",
                "CREATE INDEX IF NOT EXISTS ix_companies_industry ON companies(industry)",
                "CREATE INDEX IF NOT EXISTS ix_contacts_status ON contacts(status)",
                "CREATE INDEX IF NOT EXISTS ix_activities_entity ON activities(entity_type, entity_id)",
            ]:
                try:
                    await conn.execute(idx_sql)
                except Exception:
                    pass

            column_migrations = [
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS sales_code VARCHAR(100)",
                "CREATE INDEX IF NOT EXISTS ix_leads_sales_code ON leads(sales_code)",
                "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS sales_code VARCHAR(100)",
                "CREATE INDEX IF NOT EXISTS ix_contacts_sales_code ON contacts(sales_code)",
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS segment VARCHAR(100)",
                "CREATE INDEX IF NOT EXISTS ix_companies_segment ON companies(segment)",
                "ALTER TABLE proposal_templates ADD COLUMN IF NOT EXISTS body TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE proposal_templates ADD COLUMN IF NOT EXISTS legal_terms TEXT",
                "ALTER TABLE proposal_templates ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE",
                "ALTER TABLE proposal_templates ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
                "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS category VARCHAR(50)",
                "ALTER TABLE saved_filters ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE",
                "ALTER TABLE saved_reports ADD COLUMN IF NOT EXISTS schedule VARCHAR(20)",
                "ALTER TABLE saved_reports ADD COLUMN IF NOT EXISTS recipients TEXT",
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS pipeline_stage_id INTEGER REFERENCES pipeline_stages(id) ON DELETE SET NULL",
                "CREATE INDEX IF NOT EXISTS ix_leads_pipeline_stage_id ON leads(pipeline_stage_id)",
                "ALTER TABLE pipeline_stages ADD COLUMN IF NOT EXISTS pipeline_type VARCHAR(20) DEFAULT 'opportunity'",
                "CREATE INDEX IF NOT EXISTS ix_pipeline_stages_pipeline_type ON pipeline_stages(pipeline_type)",
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS link_creative_tier VARCHAR(10)",
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS sow_url VARCHAR(500)",
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS account_manager VARCHAR(255)",
                "ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0 NOT NULL",
                "ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ",
                # Infrastructure buildout: campaign multi-step execution
                "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS current_step INTEGER DEFAULT 0",
                "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS next_step_at TIMESTAMPTZ",
                "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS is_executing BOOLEAN DEFAULT FALSE",
                # Campaign member tracking: Date → DateTime
                "ALTER TABLE campaign_members ALTER COLUMN sent_at TYPE TIMESTAMPTZ USING sent_at::TIMESTAMPTZ",
                "ALTER TABLE campaign_members ALTER COLUMN responded_at TYPE TIMESTAMPTZ USING responded_at::TIMESTAMPTZ",
                "ALTER TABLE campaign_members ALTER COLUMN converted_at TYPE TIMESTAMPTZ USING converted_at::TIMESTAMPTZ",
                # Scheduled report delivery
                "ALTER TABLE saved_reports ADD COLUMN IF NOT EXISTS last_sent_at TIMESTAMPTZ",
                # Meta integration: Instagram fields
                "ALTER TABLE company_meta_data ADD COLUMN IF NOT EXISTS instagram_id VARCHAR(100)",
                "ALTER TABLE company_meta_data ADD COLUMN IF NOT EXISTS instagram_username VARCHAR(255)",
                "ALTER TABLE company_meta_data ADD COLUMN IF NOT EXISTS instagram_followers INTEGER",
                "ALTER TABLE company_meta_data ADD COLUMN IF NOT EXISTS instagram_media_count INTEGER",
                # Email logging: new columns on email_queue
                "ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS from_email VARCHAR(255)",
                "ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS cc TEXT",
                "ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS bcc TEXT",
            ]
            for sql in column_migrations:
                try:
                    await conn.execute(sql)
                except Exception:
                    pass

            # Create inbound_emails table if it doesn't exist
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS inbound_emails (
                        id SERIAL PRIMARY KEY,
                        resend_email_id VARCHAR(255) UNIQUE NOT NULL,
                        from_email VARCHAR(255) NOT NULL,
                        to_email VARCHAR(255) NOT NULL,
                        cc TEXT,
                        bcc TEXT,
                        subject VARCHAR(500) NOT NULL,
                        body_text TEXT,
                        body_html TEXT,
                        message_id VARCHAR(500),
                        in_reply_to VARCHAR(500),
                        attachments JSONB,
                        entity_type VARCHAR(50),
                        entity_id INTEGER,
                        received_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                await conn.execute("CREATE INDEX IF NOT EXISTS ix_inbound_emails_entity ON inbound_emails(entity_type, entity_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS ix_inbound_emails_from ON inbound_emails(from_email)")
            except Exception:
                pass

            # Create email_settings table if it doesn't exist
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS email_settings (
                        id SERIAL PRIMARY KEY,
                        daily_send_limit INTEGER NOT NULL DEFAULT 200,
                        warmup_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                        warmup_start_date DATE,
                        warmup_target_daily INTEGER NOT NULL DEFAULT 200,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
            except Exception:
                pass

            try:
                await conn.execute("""
                    UPDATE pipeline_stages SET pipeline_type = 'lead'
                    WHERE LOWER(name) IN ('new', 'contacted', 'qualified', 'nurturing', 'unqualified', 'converted')
                    AND pipeline_type != 'lead'
                """)
            except Exception:
                pass

            print("Production migrations completed successfully")
        finally:
            await conn.close()
    except Exception as e:
        print(f"Production migration error (non-fatal): {e}")


async def _init_database():
    """Initialize database tables and seed data in background."""
    try:
        await _run_production_migrations()

        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        from src.auth.models import User
        from src.core.models import Note, Tag, EntityTag, EntityShare
        from src.contacts.models import Contact
        from src.companies.models import Company
        from src.leads.models import Lead, LeadSource
        from src.opportunities.models import Opportunity, PipelineStage
        from src.activities.models import Activity
        from src.campaigns.models import Campaign, CampaignMember, EmailTemplate, EmailCampaignStep
        from src.dashboard.models import DashboardNumberCard, DashboardChart
        from src.workflows.models import WorkflowRule, WorkflowExecution
        from src.ai.models import AIEmbedding, AIConversation, AIFeedback, AIKnowledgeDocument, AIUserPreferences
        from src.whitelabel.models import Tenant, TenantSettings, TenantUser
        from src.attachments.models import Attachment
        from src.email.models import EmailQueue, InboundEmail, EmailSettings
        from src.notifications.models import Notification
        from src.filters.models import SavedFilter
        from src.reports.models import SavedReport
        from src.audit.models import AuditLog
        from src.comments.models import Comment
        from src.roles.models import Role, UserRole
        from src.webhooks.models import Webhook, WebhookDelivery
        from src.assignment.models import AssignmentRule
        from src.sequences.models import Sequence, SequenceEnrollment
        from src.quotes.models import Quote, QuoteLineItem, QuoteTemplate, ProductBundle, ProductBundleItem
        from src.payments.models import StripeCustomer, Product, Price, Payment, Subscription
        from src.proposals.models import Proposal, ProposalTemplate, ProposalView
        from src.contracts.models import Contract
        from src.meta.models import CompanyMetaData
        from src.expenses.models import Expense

        from src.database import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        from src.database import async_session_maker
        from src.roles.service import RoleService
        async with async_session_maker() as session:
            role_service = RoleService(session)
            seeded = await role_service.seed_default_roles()
            if seeded:
                await session.commit()
                print(f"Seeded {len(seeded)} default roles")
            else:
                print("Default roles already exist")

        print("Database initialized successfully")

        if getattr(settings, 'SEED_ON_STARTUP', False):
            try:
                from src.seed import seed_database
                async with async_session_maker() as session:
                    await seed_database(session)
            except ImportError:
                pass
    except Exception as e:
        print(f"Database initialization error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    from src.core.scheduler import start_scheduler, stop_scheduler

    print("Starting up CRM application...")
    asyncio.create_task(_init_database())
    start_scheduler()

    yield

    print("Shutting down CRM application...")
    stop_scheduler()
    await engine.dispose()


# Create FastAPI app
app = FastAPI(
    title="CRM API",
    description="Modern CRM with AI Assistant",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tenant resolution middleware (runs after CORS)
app.add_middleware(TenantMiddleware)

# Include routers - they already have /api prefix in their definitions
app.include_router(auth_router)
app.include_router(contacts_router)
app.include_router(companies_router)
app.include_router(leads_router)
app.include_router(opportunities_router)
app.include_router(activities_router)
app.include_router(campaigns_router)
app.include_router(dashboard_router)
app.include_router(ai_router)
app.include_router(whitelabel_router)
app.include_router(import_export_router)
app.include_router(notes_router)
app.include_router(workflows_router)
app.include_router(attachments_router)
app.include_router(dedup_router)
app.include_router(email_router)
app.include_router(notifications_router)
app.include_router(filters_router)
app.include_router(reports_router)
app.include_router(audit_router)
app.include_router(comments_router)
app.include_router(roles_router)
app.include_router(webhooks_router)
app.include_router(assignment_router)
app.include_router(sequences_router)
app.include_router(sharing_router)
app.include_router(quotes_router)
app.include_router(payments_router)
app.include_router(proposals_router)
app.include_router(contracts_router)
app.include_router(admin_router)
app.include_router(meta_router)
app.include_router(expenses_router)
app.include_router(google_calendar_router)
app.include_router(settings_router)


# Register webhook event handler with event system
from src.events.service import on as event_on
from src.webhooks.event_handler import webhook_event_handler
from src.notifications.event_handler import notification_event_handler
from src.events.service import (
    LEAD_CREATED, LEAD_UPDATED,
    CONTACT_CREATED, CONTACT_UPDATED,
    OPPORTUNITY_CREATED, OPPORTUNITY_UPDATED, OPPORTUNITY_STAGE_CHANGED,
    ACTIVITY_CREATED,
    COMPANY_CREATED, COMPANY_UPDATED,
    QUOTE_SENT, QUOTE_ACCEPTED,
    PROPOSAL_SENT, PROPOSAL_ACCEPTED,
    PAYMENT_RECEIVED,
)

for _evt in [
    LEAD_CREATED, LEAD_UPDATED,
    CONTACT_CREATED, CONTACT_UPDATED,
    OPPORTUNITY_CREATED, OPPORTUNITY_UPDATED, OPPORTUNITY_STAGE_CHANGED,
    ACTIVITY_CREATED,
    COMPANY_CREATED, COMPANY_UPDATED,
    QUOTE_SENT, QUOTE_ACCEPTED,
    PROPOSAL_SENT, PROPOSAL_ACCEPTED,
    PAYMENT_RECEIVED,
]:
    event_on(_evt, webhook_event_handler)

# Register notification event handler for key events
for _evt in [LEAD_CREATED, CONTACT_CREATED, OPPORTUNITY_STAGE_CHANGED]:
    event_on(_evt, notification_event_handler)


# Static files for production - serve frontend if dist exists
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if settings.DEBUG:
    @app.get("/api/debug/data-scope-check")
    async def debug_data_scope_check(current_user: CurrentUser):
        """Check data ownership for the currently logged-in user."""
        from sqlalchemy import select, func
        from src.database import async_session_maker
        from src.auth.models import User
        from src.contacts.models import Contact
        from src.companies.models import Company
        from src.leads.models import Lead
        from src.opportunities.models import Opportunity
        from src.activities.models import Activity
        from src.campaigns.models import Campaign

        async with async_session_maker() as session:
            # Get all users
            users_result = await session.execute(
                select(User.id, User.email, User.is_superuser)
            )
            users = [{"id": r.id, "email": r.email, "is_superuser": r.is_superuser} for r in users_result.all()]

            # Count records per owner for each entity
            entities = {
                "contacts": Contact,
                "companies": Company,
                "leads": Lead,
                "opportunities": Opportunity,
                "activities": Activity,
                "campaigns": Campaign,
            }
            ownership = {}
            for name, model in entities.items():
                result = await session.execute(
                    select(model.owner_id, func.count(model.id))
                    .group_by(model.owner_id)
                )
                ownership[name] = {str(r[0]): r[1] for r in result.all()}

            return {
                "current_user_id": current_user.id,
                "current_user_email": current_user.email,
                "users": users,
                "records_by_owner": ownership,
            }


@app.post("/api/admin/reseed-demo-data")
async def reseed_demo_data(current_user: CurrentUser):
    """Delete all demo data and re-seed it. Only the demo user gets demo data."""
    if not current_user.is_superuser:
        from src.core.router_utils import raise_forbidden
        raise_forbidden("Only superusers can reseed data")

    from sqlalchemy import select, delete
    from src.database import async_session_maker
    from src.auth.models import User
    from src.contacts.models import Contact
    from src.companies.models import Company
    from src.leads.models import Lead
    from src.opportunities.models import Opportunity
    from src.activities.models import Activity
    from src.campaigns.models import Campaign
    from src.core.models import Note, EntityTag

    async with async_session_maker() as session:
        # Find the demo user
        result = await session.execute(
            select(User).where(User.email == "demo@demo.com")
        )
        demo_user = result.scalar_one_or_none()
        if not demo_user:
            return {"error": "Demo user not found", "action": "none"}

        demo_id = demo_user.id

        # Delete demo user's data in dependency order
        # Scope EntityTag deletions to demo user's entities only
        from sqlalchemy import and_
        for etype, model in [("contacts", Contact), ("companies", Company), ("leads", Lead), ("opportunities", Opportunity)]:
            demo_ids_q = select(model.id).where(model.owner_id == demo_id)
            await session.execute(
                delete(EntityTag).where(and_(EntityTag.entity_type == etype, EntityTag.entity_id.in_(demo_ids_q)))
            )
        await session.execute(delete(Note).where(Note.created_by_id == demo_id))
        await session.execute(delete(Activity).where(Activity.owner_id == demo_id))
        await session.execute(delete(Opportunity).where(Opportunity.owner_id == demo_id))
        await session.execute(delete(Contact).where(Contact.owner_id == demo_id))
        await session.execute(delete(Company).where(Company.owner_id == demo_id))
        await session.execute(delete(Lead).where(Lead.owner_id == demo_id))
        await session.execute(delete(Campaign).where(Campaign.owner_id == demo_id))

        # Delete the demo user so seed_database will recreate everything
        await session.execute(delete(User).where(User.id == demo_id))
        await session.commit()

    # Re-run the seed
    from src.seed import seed_database
    async with async_session_maker() as session:
        await seed_database(session)

    return {"status": "success", "message": "Demo data re-seeded. Admin account has clean data, demo account has sample data."}


# Serve frontend in production (after API routes so they take precedence)
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    _CACHEABLE_EXTENSIONS = {".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".eot"}

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve SPA for all non-API routes."""
        # Never intercept API paths - let them 404 naturally
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            response = FileResponse(file_path)
            if file_path.suffix in _CACHEABLE_EXTENSIONS:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                response.headers["Cache-Control"] = "no-cache, must-revalidate"
            return response
        response = FileResponse(FRONTEND_DIST / "index.html")
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response
else:
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": "CRM API",
            "version": "1.0.0",
            "status": "running",
        }


@app.get("/api/tags")
async def list_tags(current_user: CurrentUser):
    """List all tags (cached for 5 minutes)."""
    from sqlalchemy import select
    from src.database import async_session_maker
    from src.core.models import Tag
    from src.core.cache import cached_fetch, CACHE_TAGS

    async def fetch_tags():
        async with async_session_maker() as session:
            result = await session.execute(select(Tag).order_by(Tag.name))
            tags = result.scalars().all()
            return [{"id": t.id, "name": t.name, "color": t.color} for t in tags]

    return await cached_fetch(CACHE_TAGS, "all_tags", fetch_tags)


@app.post("/api/tags")
async def create_tag(current_user: CurrentUser, name: str, color: str = "#6366f1"):
    """Create a new tag."""
    from src.database import async_session_maker
    from src.core.models import Tag
    from src.core.cache import invalidate_tags_cache

    async with async_session_maker() as session:
        tag = Tag(name=name, color=color)
        session.add(tag)
        await session.commit()
        await session.refresh(tag)
        # Invalidate cache since we added a new tag
        invalidate_tags_cache()
        return {"id": tag.id, "name": tag.name, "color": tag.color}

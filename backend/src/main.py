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

# Import routers
from src.auth.router import router as auth_router
from src.contacts.router import router as contacts_router
from src.companies.router import router as companies_router
from src.leads.router import router as leads_router
from src.opportunities.router import router as opportunities_router
from src.activities.router import router as activities_router
from src.campaigns.router import router as campaigns_router
from src.dashboard.router import router as dashboard_router
from src.ai.router import router as ai_router
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


async def _init_database():
    """Initialize database tables and seed data in background."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        from src.auth.models import User
        from src.core.models import Note, Tag, EntityTag
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
        from src.email.models import EmailQueue
        from src.notifications.models import Notification
        from src.filters.models import SavedFilter
        from src.reports.models import SavedReport
        from src.audit.models import AuditLog
        from src.comments.models import Comment
        from src.roles.models import Role, UserRole
        from src.webhooks.models import Webhook, WebhookDelivery
        from src.assignment.models import AssignmentRule
        from src.sequences.models import Sequence, SequenceEnrollment

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
    print("Starting up CRM application...")
    asyncio.create_task(_init_database())

    yield

    print("Shutting down CRM application...")
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


# Register webhook event handler with event system
from src.events.service import on as event_on
from src.webhooks.event_handler import webhook_event_handler
from src.events.service import (
    LEAD_CREATED, LEAD_UPDATED,
    CONTACT_CREATED, CONTACT_UPDATED,
    OPPORTUNITY_CREATED, OPPORTUNITY_UPDATED, OPPORTUNITY_STAGE_CHANGED,
    ACTIVITY_CREATED,
    COMPANY_CREATED, COMPANY_UPDATED,
)

for _evt in [
    LEAD_CREATED, LEAD_UPDATED,
    CONTACT_CREATED, CONTACT_UPDATED,
    OPPORTUNITY_CREATED, OPPORTUNITY_UPDATED, OPPORTUNITY_STAGE_CHANGED,
    ACTIVITY_CREATED,
    COMPANY_CREATED, COMPANY_UPDATED,
]:
    event_on(_evt, webhook_event_handler)


# Static files for production - serve frontend if dist exists
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# Serve frontend in production (after API routes so they take precedence)
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve SPA for all non-API routes."""
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
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

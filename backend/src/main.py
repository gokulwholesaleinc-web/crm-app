"""FastAPI CRM Application - Main Entry Point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.config import settings
from src.database import engine, init_db
from src.core.router_utils import CurrentUser

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup
    print("Starting up CRM application...")

    # Initialize database
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # Import all models to ensure they're registered
    from src.auth.models import User
    from src.core.models import Note, Tag, EntityTag
    from src.contacts.models import Contact
    from src.companies.models import Company
    from src.leads.models import Lead, LeadSource
    from src.opportunities.models import Opportunity, PipelineStage
    from src.activities.models import Activity
    from src.campaigns.models import Campaign, CampaignMember
    from src.dashboard.models import DashboardNumberCard, DashboardChart
    from src.ai.models import AIEmbedding, AIConversation
    from src.whitelabel.models import Tenant, TenantSettings, TenantUser

    # Create tables
    from src.database import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("Database initialized successfully")

    yield

    # Shutdown
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


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "CRM API",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


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

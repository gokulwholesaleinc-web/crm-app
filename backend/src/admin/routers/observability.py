"""Admin observability endpoints: system stats, team overview, activity feed."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from src.admin._router_helpers import _require_admin
from src.admin.schemas import (
    ActivityFeedEntry,
    SystemStats,
    TeamMemberOverview,
)
from src.audit.models import AuditLog
from src.auth.models import User
from src.companies.models import Company
from src.contacts.models import Contact
from src.core.rate_limit import limiter
from src.core.router_utils import CurrentUser, DBSession
from src.leads.models import Lead
from src.opportunities.models import Opportunity, PipelineStage
from src.payments.models import Payment
from src.proposals.models import Proposal
from src.quotes.models import Quote

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /api/admin/stats
# ---------------------------------------------------------------------------
@router.get("/stats", response_model=SystemStats)
@limiter.limit("30/minute")
async def get_system_stats(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """System-wide stats: totals and active users in last 7 days."""
    _require_admin(current_user)

    seven_days_ago = datetime.now(UTC) - timedelta(days=7)

    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_contacts = (await db.execute(select(func.count(Contact.id)))).scalar() or 0
    total_companies = (await db.execute(select(func.count(Company.id)))).scalar() or 0
    total_leads = (await db.execute(select(func.count(Lead.id)))).scalar() or 0
    total_opps = (await db.execute(select(func.count(Opportunity.id)))).scalar() or 0
    total_quotes = (await db.execute(select(func.count(Quote.id)))).scalar() or 0
    total_proposals = (await db.execute(select(func.count(Proposal.id)))).scalar() or 0
    total_payments = (await db.execute(select(func.count(Payment.id)))).scalar() or 0
    active_users = (await db.execute(
        select(func.count(User.id)).where(
            User.last_login >= seven_days_ago,
            User.is_active == True,
        )
    )).scalar() or 0

    return SystemStats(
        total_users=total_users,
        total_contacts=total_contacts,
        total_companies=total_companies,
        total_leads=total_leads,
        total_opportunities=total_opps,
        total_quotes=total_quotes,
        total_proposals=total_proposals,
        total_payments=total_payments,
        active_users_7d=active_users,
    )


# ---------------------------------------------------------------------------
# GET /api/admin/team-overview
# ---------------------------------------------------------------------------
@router.get("/team-overview", response_model=list[TeamMemberOverview])
@limiter.limit("30/minute")
async def get_team_overview(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Per-user breakdown: leads, opportunities, pipeline value, won deals."""
    _require_admin(current_user)

    users_result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.id)
    )
    users = users_result.scalars().all()

    lead_counts = dict(
        (await db.execute(
            select(Lead.owner_id, func.count(Lead.id)).group_by(Lead.owner_id)
        )).tuples().all()
    )
    opp_counts = dict(
        (await db.execute(
            select(Opportunity.owner_id, func.count(Opportunity.id)).group_by(Opportunity.owner_id)
        )).tuples().all()
    )

    # Pipeline value per user (open deals only)
    pipeline_result = await db.execute(
        select(
            Opportunity.owner_id,
            func.coalesce(func.sum(Opportunity.amount), 0),
        )
        .join(PipelineStage)
        .where(PipelineStage.is_won == False, PipelineStage.is_lost == False)
        .group_by(Opportunity.owner_id)
    )
    pipeline_values = dict(pipeline_result.tuples().all())

    # Won deals per user
    won_result = await db.execute(
        select(
            Opportunity.owner_id,
            func.count(Opportunity.id),
        )
        .join(PipelineStage)
        .where(PipelineStage.is_won == True)
        .group_by(Opportunity.owner_id)
    )
    won_counts = dict(won_result.tuples().all())

    overview = []
    for u in users:
        overview.append(TeamMemberOverview(
            user_id=u.id,
            user_name=u.full_name,
            role=u.role or "sales_rep",
            lead_count=lead_counts.get(u.id, 0),
            opportunity_count=opp_counts.get(u.id, 0),
            total_pipeline_value=float(pipeline_values.get(u.id) or 0),
            won_deals=won_counts.get(u.id, 0),
        ))
    return overview


# ---------------------------------------------------------------------------
# GET /api/admin/activity-feed
# ---------------------------------------------------------------------------
@router.get("/activity-feed", response_model=list[ActivityFeedEntry])
@limiter.limit("30/minute")
async def get_activity_feed(
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    """Recent audit log entries across all users with pagination."""
    _require_admin(current_user)

    result = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .offset(skip)
        .limit(limit)
    )
    logs = result.scalars().all()

    # Fetch user names for the feed
    user_ids = {log.user_id for log in logs if log.user_id}
    user_names = {}
    if user_ids:
        users_result = await db.execute(
            select(User.id, User.full_name).where(User.id.in_(user_ids))
        )
        user_names = dict(users_result.tuples().all())

    entries = []
    for log in logs:
        entries.append(ActivityFeedEntry(
            id=log.id,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            action=log.action,
            user_id=log.user_id,
            user_name=user_names.get(log.user_id) if log.user_id else None,
            timestamp=log.timestamp,
            changes=log.changes,
        ))
    return entries

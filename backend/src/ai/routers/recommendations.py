"""AI recommendations and predictive endpoints."""

import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from datetime import date as date_type

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from src.activities.models import Activity
from src.ai.recommendations import RecommendationEngine
from src.ai.schemas import (
    NextBestAction,
    Recommendation,
    RecommendationsResponse,
)
from src.core.router_utils import CurrentUser, DBSession, raise_not_found
from src.opportunities.models import Opportunity

router = APIRouter()

_recs_cache: dict[int, tuple[float, "RecommendationsResponse"]] = {}
_RECS_CACHE_TTL = 60


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get prioritized action recommendations."""
    cached = _recs_cache.get(current_user.id)
    if cached and (time.monotonic() - cached[0]) < _RECS_CACHE_TTL:
        return cached[1]

    engine = RecommendationEngine(db)
    recs = await engine.get_recommendations(current_user.id)

    result = RecommendationsResponse(
        recommendations=[Recommendation(**r) for r in recs]
    )
    _recs_cache[current_user.id] = (time.monotonic(), result)
    return result


@router.get("/next-action/{entity_type}/{entity_id}", response_model=NextBestAction)
async def get_next_best_action(
    entity_type: str,
    entity_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get the recommended next action for an entity."""
    engine = RecommendationEngine(db)
    result = await engine.get_next_best_action(entity_type, entity_id)

    if "error" in result:
        raise_not_found(result["error"])

    return NextBestAction(**result)


@router.get("/predict/opportunity/{opportunity_id}")
async def predict_win_probability(
    opportunity_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Predict the win probability for an opportunity using heuristic scoring."""
    result = await db.execute(
        select(Opportunity).where(Opportunity.id == opportunity_id)
    )
    opp = result.scalar_one_or_none()

    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    stage = opp.pipeline_stage
    factors = {}

    # If deal is already won or lost, return immediately
    if stage.is_won:
        return {
            "opportunity_id": opportunity_id,
            "win_probability": 100,
            "base_stage_probability": stage.probability,
            "factors": {"stage": "won"},
        }
    if stage.is_lost:
        return {
            "opportunity_id": opportunity_id,
            "win_probability": 0,
            "base_stage_probability": stage.probability,
            "factors": {"stage": "lost"},
        }

    # Start with stage probability as base
    base_prob = stage.probability
    adjusted_prob = float(base_prob)

    # Factor: has contact assigned
    if opp.contact_id:
        adjusted_prob += 5
        factors["has_contact"] = 5

    # Factor: has company assigned
    if opp.company_id:
        adjusted_prob += 3
        factors["has_company"] = 3

    # Factor: has expected close date
    if opp.expected_close_date:
        days_until_close = (opp.expected_close_date - date_type.today()).days
        if days_until_close < 0:
            adjusted_prob -= 10
            factors["overdue_penalty"] = -10
        elif days_until_close <= 30:
            adjusted_prob += 5
            factors["closing_soon_bonus"] = 5

    # Factor: recent activity count
    activity_result = await db.execute(
        select(func.count(Activity.id))
        .where(Activity.entity_type == "opportunities")
        .where(Activity.entity_id == opportunity_id)
    )
    activity_count = activity_result.scalar() or 0

    if activity_count >= 3:
        adjusted_prob += 5
        factors["high_activity_bonus"] = 5
    elif activity_count == 0:
        adjusted_prob -= 5
        factors["no_activity_penalty"] = -5

    # Clamp to 0-100
    win_probability = max(0, min(100, int(round(adjusted_prob))))

    return {
        "opportunity_id": opportunity_id,
        "win_probability": win_probability,
        "base_stage_probability": base_prob,
        "factors": factors,
    }


@router.get("/suggest/next-action/{entity_type}/{entity_id}")
async def suggest_next_action(
    entity_type: str,
    entity_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Suggest the next best action for an entity."""
    engine = RecommendationEngine(db)
    result = await engine.get_next_best_action(entity_type, entity_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.get("/summary/{entity_type}/{entity_id}")
async def get_activity_summary(
    entity_type: str,
    entity_id: int,
    current_user: CurrentUser,
    db: DBSession,
    days: int = Query(30, ge=1, le=365),
):
    """Get activity summary for an entity over a time period."""
    cutoff = datetime.now(UTC) - timedelta(days=days)

    # Fetch activities for the entity within the time period
    result = await db.execute(
        select(Activity)
        .where(Activity.entity_type == entity_type)
        .where(Activity.entity_id == entity_id)
        .where(Activity.created_at > cutoff)
        .order_by(Activity.created_at.desc())
    )
    activities = result.scalars().all()

    total = len(activities)
    by_type = dict(Counter(a.activity_type for a in activities))

    last_activity = None
    if activities:
        last = activities[0]
        last_activity = {
            "id": last.id,
            "type": last.activity_type,
            "subject": last.subject,
            "date": last.created_at.isoformat() if last.created_at else None,
        }

    if total == 0:
        summary_text = f"No activities recorded in the last {days} days."
    else:
        type_parts = [f"{count} {atype}(s)" for atype, count in by_type.items()]
        summary_text = f"{total} activities in the last {days} days: {', '.join(type_parts)}."

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "period_days": days,
        "total_activities": total,
        "by_type": by_type,
        "last_activity": last_activity,
        "summary": summary_text,
    }

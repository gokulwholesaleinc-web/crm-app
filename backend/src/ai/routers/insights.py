"""AI insights endpoints."""

from fastapi import APIRouter

from src.ai.insights import InsightsGenerator
from src.ai.learning_service import AILearningService
from src.ai.schemas import (
    DailySummaryResponse,
    EntityInsightsResponse,
    InsightResponse,
)
from src.core.router_utils import CurrentUser, DBSession, raise_not_found

router = APIRouter()


@router.get("/insights/lead/{lead_id}", response_model=InsightResponse)
async def get_lead_insights(
    lead_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get AI-powered insights for a lead."""
    generator = InsightsGenerator(db)
    result = await generator.get_lead_insights(lead_id)

    if "error" in result:
        raise_not_found(result["error"])

    return InsightResponse(
        lead_data=result.get("lead_data"),
        insights=result.get("insights", ""),
    )


@router.get("/insights/opportunity/{opportunity_id}", response_model=InsightResponse)
async def get_opportunity_insights(
    opportunity_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get AI-powered insights for an opportunity."""
    generator = InsightsGenerator(db)
    result = await generator.get_opportunity_insights(opportunity_id)

    if "error" in result:
        raise_not_found(result["error"])

    return InsightResponse(
        opportunity_data=result.get("opportunity_data"),
        insights=result.get("insights", ""),
    )


@router.get("/summary/daily", response_model=DailySummaryResponse)
async def get_daily_summary(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get AI-generated daily summary."""
    generator = InsightsGenerator(db)
    result = await generator.get_daily_summary(current_user.id)

    return DailySummaryResponse(
        data=result.get("data", {}),
        summary=result.get("summary", ""),
    )


@router.get("/entity-insights/{entity_type}/{entity_id}", response_model=EntityInsightsResponse)
async def get_entity_insights(
    entity_type: str,
    entity_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get AI-powered insights for a specific entity."""
    service = AILearningService(db)
    result = await service.get_entity_insights(entity_type, entity_id, current_user.id)
    return EntityInsightsResponse(**result)

"""AI Assistant API routes."""

from typing import Optional
from fastapi import APIRouter, Query
from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, raise_not_found
from src.ai.schemas import (
    ChatRequest,
    ChatResponse,
    InsightResponse,
    DailySummaryResponse,
    RecommendationsResponse,
    Recommendation,
    NextBestAction,
    SearchResponse,
    SimilarContentResult,
)
from src.ai.query_processor import QueryProcessor
from src.ai.insights import InsightsGenerator
from src.ai.recommendations import RecommendationEngine
from src.ai.embeddings import EmbeddingService

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Chat with the AI assistant using natural language."""
    processor = QueryProcessor(db)
    result = await processor.process_query(request.message, current_user.id)

    return ChatResponse(
        response=result.get("response", ""),
        data=result.get("data"),
        function_called=result.get("function_called"),
        session_id=request.session_id,
    )


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


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get prioritized action recommendations."""
    engine = RecommendationEngine(db)
    recs = await engine.get_recommendations(current_user.id)

    return RecommendationsResponse(
        recommendations=[Recommendation(**r) for r in recs]
    )


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


@router.get("/search", response_model=SearchResponse)
async def semantic_search(
    query: str,
    current_user: CurrentUser,
    db: DBSession,
    entity_types: Optional[str] = None,
    limit: int = Query(5, ge=1, le=20),
):
    """Perform semantic search across CRM content."""
    service = EmbeddingService(db)

    parsed_types = None
    if entity_types:
        parsed_types = entity_types.split(",")

    results = await service.search_similar(
        query=query,
        entity_types=parsed_types,
        limit=limit,
    )

    return SearchResponse(
        results=[SimilarContentResult(**r) for r in results]
    )

"""AI Assistant API routes."""

from typing import Optional
from fastapi import APIRouter, Query, UploadFile, File, HTTPException
from sqlalchemy import select, func
from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, raise_not_found, raise_bad_request
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
    FeedbackRequest,
    FeedbackResponse,
    FeedbackStatsResponse,
    KnowledgeDocumentResponse,
    KnowledgeDocumentListResponse,
    UserPreferencesRequest,
    UserPreferencesResponse,
    ConfirmActionRequest,
    ConfirmActionResponse,
)
from src.ai.models import AIFeedback, AIUserPreferences
from src.ai.query_processor import QueryProcessor
from src.ai.insights import InsightsGenerator
from src.ai.recommendations import RecommendationEngine
from src.ai.embeddings import EmbeddingService
from src.ai.knowledge_base import KnowledgeBaseService

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Chat with the AI assistant using natural language."""
    processor = QueryProcessor(db)
    result = await processor.process_query(
        request.message, current_user.id, session_id=request.session_id
    )

    return ChatResponse(
        response=result.get("response", ""),
        data=result.get("data"),
        function_called=result.get("function_called"),
        session_id=result.get("session_id", request.session_id),
        confirmation_required=result.get("confirmation_required", False),
        pending_action=result.get("pending_action"),
        actions_taken=result.get("actions_taken", []),
    )


@router.post("/confirm-action", response_model=ConfirmActionResponse)
async def confirm_action(
    request: ConfirmActionRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Confirm and execute a high-risk AI action that was previously flagged."""
    if not request.confirmed:
        return ConfirmActionResponse(
            response="Action cancelled by user.",
            data=None,
        )

    processor = QueryProcessor(db)
    result = await processor.execute_confirmed_action(
        function_name=request.function_name,
        arguments=request.arguments,
        user_id=current_user.id,
        session_id=request.session_id,
    )

    return ConfirmActionResponse(
        response=result.get("response", ""),
        data=result.get("data"),
        function_called=result.get("function_called"),
        actions_taken=result.get("actions_taken", []),
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


# --- Feedback endpoints ---

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Submit feedback on an AI response."""
    if request.feedback not in ("positive", "negative", "correction"):
        raise_bad_request("Feedback must be 'positive', 'negative', or 'correction'")

    if request.feedback == "correction" and not request.correction_text:
        raise_bad_request("Correction text is required for correction feedback")

    feedback = AIFeedback(
        user_id=current_user.id,
        session_id=request.session_id,
        query=request.query,
        response=request.response,
        retrieved_context_ids=request.retrieved_context_ids,
        feedback=request.feedback,
        correction_text=request.correction_text,
    )
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)

    return FeedbackResponse(
        id=feedback.id,
        feedback=feedback.feedback,
        created_at=feedback.created_at,
    )


@router.get("/feedback/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get feedback statistics."""
    total_result = await db.execute(
        select(func.count(AIFeedback.id))
    )
    total = total_result.scalar() or 0

    positive_result = await db.execute(
        select(func.count(AIFeedback.id)).where(AIFeedback.feedback == "positive")
    )
    positive = positive_result.scalar() or 0

    negative_result = await db.execute(
        select(func.count(AIFeedback.id)).where(AIFeedback.feedback == "negative")
    )
    negative = negative_result.scalar() or 0

    corrections_result = await db.execute(
        select(func.count(AIFeedback.id)).where(AIFeedback.feedback == "correction")
    )
    corrections = corrections_result.scalar() or 0

    return FeedbackStatsResponse(
        total=total,
        positive=positive,
        negative=negative,
        corrections=corrections,
    )


# --- Knowledge Base endpoints ---

ALLOWED_CONTENT_TYPES = {"text/plain", "text/csv", "application/pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/knowledge-base/upload", response_model=KnowledgeDocumentResponse)
async def upload_knowledge_document(
    current_user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
):
    """Upload a document to the knowledge base."""
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise_bad_request(
            f"Unsupported file type: {file.content_type}. Allowed: {', '.join(ALLOWED_CONTENT_TYPES)}"
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise_bad_request("File size exceeds 10MB limit")

    service = KnowledgeBaseService(db)
    doc = await service.upload_document(
        filename=file.filename or "unknown",
        content=content,
        content_type=file.content_type or "text/plain",
        user_id=current_user.id,
    )

    return KnowledgeDocumentResponse(
        id=doc.id,
        filename=doc.filename,
        content_type=doc.content_type,
        chunk_count=doc.chunk_count,
        created_at=doc.created_at,
    )


@router.get("/knowledge-base", response_model=KnowledgeDocumentListResponse)
async def list_knowledge_documents(
    current_user: CurrentUser,
    db: DBSession,
):
    """List all knowledge base documents."""
    service = KnowledgeBaseService(db)
    docs = await service.list_documents(current_user.id)

    return KnowledgeDocumentListResponse(
        documents=[
            KnowledgeDocumentResponse(
                id=d.id,
                filename=d.filename,
                content_type=d.content_type,
                chunk_count=d.chunk_count,
                created_at=d.created_at,
            )
            for d in docs
        ]
    )


@router.delete("/knowledge-base/{doc_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_knowledge_document(
    doc_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a knowledge base document."""
    service = KnowledgeBaseService(db)
    doc = await service.delete_document(doc_id, current_user.id)

    if not doc:
        raise_not_found("Knowledge base document", doc_id)


# --- User Preferences endpoints ---

@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_preferences(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get user AI preferences."""
    result = await db.execute(
        select(AIUserPreferences).where(
            AIUserPreferences.user_id == current_user.id
        )
    )
    prefs = result.scalar_one_or_none()

    if not prefs:
        # Return defaults
        prefs = AIUserPreferences(
            id=0,
            user_id=current_user.id,
            preferred_communication_style="professional",
            priority_entities=None,
            custom_instructions=None,
        )

    return UserPreferencesResponse.model_validate(prefs)


@router.put("/preferences", response_model=UserPreferencesResponse)
async def update_preferences(
    request: UserPreferencesRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update user AI preferences."""
    result = await db.execute(
        select(AIUserPreferences).where(
            AIUserPreferences.user_id == current_user.id
        )
    )
    prefs = result.scalar_one_or_none()

    if prefs:
        if request.preferred_communication_style is not None:
            prefs.preferred_communication_style = request.preferred_communication_style
        if request.priority_entities is not None:
            prefs.priority_entities = request.priority_entities
        if request.custom_instructions is not None:
            prefs.custom_instructions = request.custom_instructions
    else:
        prefs = AIUserPreferences(
            user_id=current_user.id,
            preferred_communication_style=request.preferred_communication_style or "professional",
            priority_entities=request.priority_entities,
            custom_instructions=request.custom_instructions,
        )
        db.add(prefs)

    await db.flush()
    await db.refresh(prefs)

    return UserPreferencesResponse.model_validate(prefs)


# =========================================================================
# Predictive AI endpoints
# =========================================================================


@router.get("/predict/opportunity/{opportunity_id}")
async def predict_win_probability(
    opportunity_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Predict win probability for an opportunity using heuristic scoring."""
    from src.opportunities.models import Opportunity, PipelineStage
    from src.activities.models import Activity
    from datetime import datetime, timedelta, timezone

    result = await db.execute(
        select(Opportunity).where(Opportunity.id == opportunity_id)
    )
    opp = result.scalar_one_or_none()
    if not opp:
        raise_not_found("Opportunity", opportunity_id)

    stage = opp.pipeline_stage

    # Won/Lost overrides
    if stage.is_won:
        return {
            "opportunity_id": opp.id,
            "win_probability": 100,
            "base_stage_probability": stage.probability,
            "factors": {"stage_won": True},
        }
    if stage.is_lost:
        return {
            "opportunity_id": opp.id,
            "win_probability": 0,
            "base_stage_probability": stage.probability,
            "factors": {"stage_lost": True},
        }

    # Base probability from stage
    base_prob = stage.probability
    factors = {}

    # Factor: has contact (+5)
    if opp.contact_id:
        factors["has_contact"] = 5
    # Factor: has company (+3)
    if opp.company_id:
        factors["has_company"] = 3
    # Factor: closing soon (+5)
    if opp.expected_close_date:
        days_until = (opp.expected_close_date - datetime.now(timezone.utc).date()).days
        if 0 < days_until <= 30:
            factors["closing_soon"] = 5
        elif days_until < 0:
            factors["overdue"] = -10

    # Factor: recent activity count
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    activity_result = await db.execute(
        select(func.count(Activity.id)).where(
            Activity.entity_type == "opportunities",
            Activity.entity_id == opp.id,
            Activity.created_at >= thirty_days_ago,
        )
    )
    activity_count = activity_result.scalar() or 0
    if activity_count >= 3:
        factors["high_activity_bonus"] = 5

    # Calculate final probability
    adjustments = sum(factors.values())
    final_prob = max(0, min(100, base_prob + adjustments))

    return {
        "opportunity_id": opp.id,
        "win_probability": final_prob,
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
        raise_not_found(result["error"])

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
    from src.activities.models import Activity
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(Activity).where(
            Activity.entity_type == entity_type,
            Activity.entity_id == entity_id,
            Activity.created_at >= cutoff,
        ).order_by(Activity.created_at.desc())
    )
    activities = result.scalars().all()

    # Count by type
    by_type: dict = {}
    for act in activities:
        by_type[act.activity_type] = by_type.get(act.activity_type, 0) + 1

    total = len(activities)

    # Last activity info
    last_activity = None
    if activities:
        last = activities[0]
        last_activity = {
            "id": last.id,
            "type": last.activity_type,
            "subject": last.subject,
            "date": last.created_at.isoformat() if last.created_at else None,
        }

    # Generate summary text
    if total == 0:
        summary = f"No activities recorded in the last {days} days."
    else:
        type_parts = [f"{count} {atype}(s)" for atype, count in by_type.items()]
        summary = f"{total} activities in the last {days} days: {', '.join(type_parts)}."

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "period_days": days,
        "total_activities": total,
        "by_type": by_type,
        "last_activity": last_activity,
        "summary": summary,
    }

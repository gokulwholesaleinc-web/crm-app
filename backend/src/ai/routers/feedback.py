"""AI feedback endpoints."""

from fastapi import APIRouter
from sqlalchemy import func, select

from src.ai.models import AIFeedback
from src.ai.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    FeedbackStatsResponse,
)
from src.core.router_utils import CurrentUser, DBSession, raise_bad_request

router = APIRouter()

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

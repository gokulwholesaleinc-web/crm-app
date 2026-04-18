"""AI preferences and learning endpoints."""

from fastapi import APIRouter
from sqlalchemy import select

from src.ai.learning_service import AILearningService
from src.ai.models import AIUserPreferences
from src.ai.schemas import (
    AILearningListResponse,
    AILearningResponse,
    SmartSuggestion,
    SmartSuggestionsResponse,
    TeachAIRequest,
    UserPreferencesRequest,
    UserPreferencesResponse,
)
from src.core.constants import HTTPStatus
from src.core.router_utils import CurrentUser, DBSession, raise_not_found

router = APIRouter()

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


# --- AI Learning endpoints ---


@router.get("/learnings", response_model=AILearningListResponse)
async def get_learnings(
    current_user: CurrentUser,
    db: DBSession,
    category: str | None = None,
):
    """Get all AI learnings for the current user."""
    service = AILearningService(db)
    learnings = await service.get_learnings(current_user.id, category=category)
    return AILearningListResponse(
        learnings=[AILearningResponse.model_validate(l) for l in learnings]
    )


@router.delete("/learnings/{learning_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_learning(
    learning_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a specific AI learning."""
    service = AILearningService(db)
    deleted = await service.delete_learning(learning_id, current_user.id)
    if not deleted:
        raise_not_found("AI learning", learning_id)


@router.post("/teach", response_model=AILearningResponse)
async def teach_ai(
    request: TeachAIRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Teach the AI a new preference or fact."""
    service = AILearningService(db)
    learning = await service.learn_preference(
        user_id=current_user.id,
        category=request.category,
        key=request.key,
        value=request.value,
    )
    return AILearningResponse.model_validate(learning)


@router.get("/smart-suggestions", response_model=SmartSuggestionsResponse)
async def get_smart_suggestions(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get personalized smart suggestions."""
    service = AILearningService(db)
    suggestions = await service.generate_smart_suggestions(current_user.id)
    return SmartSuggestionsResponse(
        suggestions=[SmartSuggestion(**s) for s in suggestions]
    )

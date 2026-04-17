"""Pydantic schemas for AI module."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ChatMessage(BaseModel):
    role: str  # user, assistant
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    data: dict[str, Any] | None = None
    function_called: str | None = None
    session_id: str | None = None
    confirmation_required: bool = False
    pending_action: dict[str, Any] | None = None
    actions_taken: list[dict[str, Any]] = []


class InsightResponse(BaseModel):
    lead_data: dict[str, Any] | None = None
    opportunity_data: dict[str, Any] | None = None
    insights: str


class DailySummaryResponse(BaseModel):
    data: dict[str, Any]
    summary: str


class Recommendation(BaseModel):
    type: str
    priority: str
    title: str
    description: str
    action: str
    entity_type: str | None = None
    entity_id: int | None = None
    activity_id: int | None = None
    amount: float | None = None
    score: int | None = None


class RecommendationsResponse(BaseModel):
    recommendations: list[Recommendation]


class NextBestAction(BaseModel):
    action: str
    activity_type: str | None = None
    reason: str


class SimilarContentResult(BaseModel):
    entity_type: str
    entity_id: int
    content: str
    content_type: str
    similarity: float


class SearchResponse(BaseModel):
    results: list[SimilarContentResult]


# Feedback schemas
class FeedbackRequest(BaseModel):
    session_id: str | None = None
    query: str
    response: str
    retrieved_context_ids: list[int] | None = None
    feedback: str  # positive, negative, correction
    correction_text: str | None = None


class FeedbackResponse(BaseModel):
    id: int
    feedback: str
    created_at: datetime


class FeedbackStatsResponse(BaseModel):
    total: int
    positive: int
    negative: int
    corrections: int


# Knowledge base schemas
class KnowledgeDocumentResponse(BaseModel):
    id: int
    filename: str
    content_type: str
    chunk_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeDocumentListResponse(BaseModel):
    documents: list[KnowledgeDocumentResponse]


# User preferences schemas
class UserPreferencesRequest(BaseModel):
    preferred_communication_style: str | None = None
    priority_entities: dict[str, Any] | None = None
    custom_instructions: str | None = None


class UserPreferencesResponse(BaseModel):
    id: int
    user_id: int
    preferred_communication_style: str | None = None
    priority_entities: dict[str, Any] | None = None
    custom_instructions: str | None = None

    model_config = ConfigDict(from_attributes=True)


# AI Action confirmation schemas
class ConfirmActionRequest(BaseModel):
    session_id: str
    function_name: str
    arguments: dict[str, Any]
    confirmed: bool = True


class ConfirmActionResponse(BaseModel):
    response: str
    data: dict[str, Any] | None = None
    function_called: str | None = None
    actions_taken: list[dict[str, Any]] = []


class AIActionLogResponse(BaseModel):
    id: int
    user_id: int
    session_id: str | None = None
    function_name: str
    arguments: dict[str, Any] | None = None
    risk_level: str
    was_confirmed: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# AI Learning schemas
class AILearningResponse(BaseModel):
    id: int
    user_id: int
    category: str
    key: str
    value: str
    confidence: float
    times_reinforced: int
    last_used_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AILearningListResponse(BaseModel):
    learnings: list[AILearningResponse]


class TeachAIRequest(BaseModel):
    category: str
    key: str
    value: str


class SmartSuggestion(BaseModel):
    type: str
    priority: str
    title: str
    description: str
    action: str
    entity_type: str | None = None
    entity_id: int | None = None


class SmartSuggestionsResponse(BaseModel):
    suggestions: list[SmartSuggestion]


class EntityInsightsResponse(BaseModel):
    entity_type: str
    entity_id: int
    insights: list[dict[str, Any]]
    suggestions: list[str]

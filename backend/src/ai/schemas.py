"""Pydantic schemas for AI module."""

from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, ConfigDict


class ChatMessage(BaseModel):
    role: str  # user, assistant
    content: str


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    data: Optional[Dict[str, Any]] = None
    function_called: Optional[str] = None
    session_id: Optional[str] = None
    confirmation_required: bool = False
    pending_action: Optional[Dict[str, Any]] = None
    actions_taken: List[Dict[str, Any]] = []


class InsightResponse(BaseModel):
    lead_data: Optional[Dict[str, Any]] = None
    opportunity_data: Optional[Dict[str, Any]] = None
    insights: str


class DailySummaryResponse(BaseModel):
    data: Dict[str, Any]
    summary: str


class Recommendation(BaseModel):
    type: str
    priority: str
    title: str
    description: str
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    activity_id: Optional[int] = None
    amount: Optional[float] = None
    score: Optional[int] = None


class RecommendationsResponse(BaseModel):
    recommendations: List[Recommendation]


class NextBestAction(BaseModel):
    action: str
    activity_type: Optional[str] = None
    reason: str


class SimilarContentResult(BaseModel):
    entity_type: str
    entity_id: int
    content: str
    content_type: str
    similarity: float


class SearchResponse(BaseModel):
    results: List[SimilarContentResult]


# Feedback schemas
class FeedbackRequest(BaseModel):
    session_id: Optional[str] = None
    query: str
    response: str
    retrieved_context_ids: Optional[List[int]] = None
    feedback: str  # positive, negative, correction
    correction_text: Optional[str] = None


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
    documents: List[KnowledgeDocumentResponse]


# User preferences schemas
class UserPreferencesRequest(BaseModel):
    preferred_communication_style: Optional[str] = None
    priority_entities: Optional[Dict[str, Any]] = None
    custom_instructions: Optional[str] = None


class UserPreferencesResponse(BaseModel):
    id: int
    user_id: int
    preferred_communication_style: Optional[str] = None
    priority_entities: Optional[Dict[str, Any]] = None
    custom_instructions: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# AI Action confirmation schemas
class ConfirmActionRequest(BaseModel):
    session_id: str
    function_name: str
    arguments: Dict[str, Any]
    confirmed: bool = True


class ConfirmActionResponse(BaseModel):
    response: str
    data: Optional[Dict[str, Any]] = None
    function_called: Optional[str] = None
    actions_taken: List[Dict[str, Any]] = []


class AIActionLogResponse(BaseModel):
    id: int
    user_id: int
    session_id: Optional[str] = None
    function_name: str
    arguments: Optional[Dict[str, Any]] = None
    risk_level: str
    was_confirmed: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

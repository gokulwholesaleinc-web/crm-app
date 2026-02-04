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

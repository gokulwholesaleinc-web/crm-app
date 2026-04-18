"""AI Assistant API routes — composed from sub-routers."""
from fastapi import APIRouter

from src.ai.routers import chat, feedback, insights, knowledge_base, preferences, recommendations

router = APIRouter(prefix="/api/ai", tags=["ai"])
router.include_router(chat.router)
router.include_router(insights.router)
router.include_router(recommendations.router)
router.include_router(feedback.router)
router.include_router(knowledge_base.router)
router.include_router(preferences.router)

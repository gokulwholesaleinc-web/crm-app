"""AI chat and search endpoints."""

from fastapi import APIRouter, Query

from src.ai.embeddings import EmbeddingService
from src.ai.query_processor import QueryProcessor
from src.ai.schemas import (
    ChatRequest,
    ChatResponse,
    ConfirmActionRequest,
    ConfirmActionResponse,
    SearchResponse,
    SimilarContentResult,
)
from src.core.router_utils import CurrentUser, DBSession

router = APIRouter()


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


@router.get("/search", response_model=SearchResponse)
async def semantic_search(
    query: str,
    current_user: CurrentUser,
    db: DBSession,
    entity_types: str | None = None,
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

"""AI knowledge base endpoints."""

from fastapi import APIRouter, File, UploadFile

from src.ai.knowledge_base import KnowledgeBaseService
from src.ai.schemas import (
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
)
from src.core.constants import HTTPStatus
from src.core.router_utils import CurrentUser, DBSession, raise_bad_request, raise_not_found

router = APIRouter()

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

"""Knowledge base ingestion service for document upload and chunking."""

import io
import csv
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.ai.models import AIKnowledgeDocument, AIEmbedding
from src.ai.embeddings import EmbeddingService


# Approximate tokens per character (conservative estimate)
CHARS_PER_TOKEN = 4
CHUNK_SIZE_TOKENS = 800
CHUNK_OVERLAP_TOKENS = 100
CHUNK_SIZE_CHARS = CHUNK_SIZE_TOKENS * CHARS_PER_TOKEN
CHUNK_OVERLAP_CHARS = CHUNK_OVERLAP_TOKENS * CHARS_PER_TOKEN


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> List[str]:
    """Split text into overlapping chunks."""
    if not text or not text.strip():
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size

        # Try to break at a sentence or paragraph boundary
        if end < text_len:
            # Look for paragraph break
            newline_pos = text.rfind("\n\n", start, end)
            if newline_pos > start + chunk_size // 2:
                end = newline_pos + 2
            else:
                # Look for sentence break
                period_pos = text.rfind(". ", start, end)
                if period_pos > start + chunk_size // 2:
                    end = period_pos + 2

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap
        if start >= text_len:
            break

    return chunks


def parse_csv_content(content: bytes) -> str:
    """Parse CSV content into readable text."""
    text_content = content.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text_content))
    rows = list(reader)

    if not rows:
        return ""

    headers = rows[0]
    lines = []

    for row in rows[1:]:
        parts = []
        for i, val in enumerate(row):
            if val.strip():
                header = headers[i] if i < len(headers) else f"column_{i}"
                parts.append(f"{header}: {val}")
        if parts:
            lines.append("; ".join(parts))

    return "\n".join(lines)


def parse_text_content(content: bytes) -> str:
    """Parse plain text content."""
    return content.decode("utf-8", errors="replace")


class KnowledgeBaseService:
    """Service for managing knowledge base documents."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedding_service = EmbeddingService(db)

    async def upload_document(
        self,
        filename: str,
        content: bytes,
        content_type: str,
        user_id: int,
    ) -> AIKnowledgeDocument:
        """Parse, chunk, embed, and store a document."""
        # Parse content based on type
        if content_type == "text/csv" or filename.endswith(".csv"):
            text = parse_csv_content(content)
        else:
            # Default to plain text parsing
            text = parse_text_content(content)

        # Chunk the text
        chunks = chunk_text(text)

        # Create document record
        doc = AIKnowledgeDocument(
            filename=filename,
            content_type=content_type,
            chunk_count=len(chunks),
            user_id=user_id,
        )
        self.db.add(doc)
        await self.db.flush()
        await self.db.refresh(doc)

        # Create embeddings for each chunk
        for i, chunk in enumerate(chunks):
            await self.embedding_service.store_embedding(
                entity_type="knowledge_base",
                entity_id=doc.id,
                content=chunk,
                content_type=f"chunk_{i}",
            )

        await self.db.flush()
        return doc

    async def list_documents(self, user_id: int) -> List[AIKnowledgeDocument]:
        """List all knowledge base documents for a user."""
        result = await self.db.execute(
            select(AIKnowledgeDocument)
            .where(AIKnowledgeDocument.user_id == user_id)
            .order_by(AIKnowledgeDocument.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_document(self, doc_id: int, user_id: int) -> Optional[AIKnowledgeDocument]:
        """Delete a knowledge base document and its embeddings."""
        result = await self.db.execute(
            select(AIKnowledgeDocument).where(
                AIKnowledgeDocument.id == doc_id,
                AIKnowledgeDocument.user_id == user_id,
            )
        )
        doc = result.scalar_one_or_none()

        if not doc:
            return None

        # Delete associated embeddings
        await self.embedding_service.delete_embedding(
            entity_type="knowledge_base",
            entity_id=doc.id,
        )

        await self.db.delete(doc)
        await self.db.flush()
        return doc

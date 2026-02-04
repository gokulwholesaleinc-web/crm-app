"""Embedding service for RAG with pgvector."""

from typing import List, Optional, Dict, Any
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI
from src.config import settings
from src.ai.models import AIEmbedding


class EmbeddingService:
    """Service for creating and searching embeddings."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self.model = "text-embedding-3-small"

    async def create_embedding(self, text: str) -> Optional[List[float]]:
        """Create an embedding for the given text."""
        if not self.client:
            return None

        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error creating embedding: {e}")
            return None

    async def store_embedding(
        self,
        entity_type: str,
        entity_id: int,
        content: str,
        content_type: str = "description",
    ) -> Optional[AIEmbedding]:
        """Create and store an embedding for entity content."""
        embedding_vector = await self.create_embedding(content)
        if not embedding_vector:
            return None

        # Check if embedding already exists for this entity/content_type
        existing = await self.db.execute(
            select(AIEmbedding).where(
                AIEmbedding.entity_type == entity_type,
                AIEmbedding.entity_id == entity_id,
                AIEmbedding.content_type == content_type,
            )
        )
        existing_embedding = existing.scalar_one_or_none()

        if existing_embedding:
            # Update existing
            existing_embedding.content = content
            existing_embedding.embedding = embedding_vector
            await self.db.flush()
            return existing_embedding
        else:
            # Create new
            new_embedding = AIEmbedding(
                entity_type=entity_type,
                entity_id=entity_id,
                content=content,
                content_type=content_type,
                embedding=embedding_vector,
            )
            self.db.add(new_embedding)
            await self.db.flush()
            await self.db.refresh(new_embedding)
            return new_embedding

    async def search_similar(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 5,
        threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar content using cosine similarity.

        Returns list of matches with entity info and similarity score.
        """
        query_embedding = await self.create_embedding(query)
        if not query_embedding:
            return []

        # Build query with cosine similarity
        # pgvector uses <=> for cosine distance (1 - similarity)
        sql = """
            SELECT
                entity_type,
                entity_id,
                content,
                content_type,
                1 - (embedding <=> :query_embedding::vector) as similarity
            FROM ai_embeddings
            WHERE 1 - (embedding <=> :query_embedding::vector) > :threshold
        """

        if entity_types:
            sql += " AND entity_type = ANY(:entity_types)"

        sql += " ORDER BY similarity DESC LIMIT :limit"

        params = {
            "query_embedding": str(query_embedding),
            "threshold": threshold,
            "limit": limit,
        }
        if entity_types:
            params["entity_types"] = entity_types

        result = await self.db.execute(text(sql), params)
        rows = result.fetchall()

        return [
            {
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "content": row.content,
                "content_type": row.content_type,
                "similarity": float(row.similarity),
            }
            for row in rows
        ]

    async def delete_embedding(
        self,
        entity_type: str,
        entity_id: int,
        content_type: Optional[str] = None,
    ) -> None:
        """Delete embeddings for an entity."""
        query = select(AIEmbedding).where(
            AIEmbedding.entity_type == entity_type,
            AIEmbedding.entity_id == entity_id,
        )
        if content_type:
            query = query.where(AIEmbedding.content_type == content_type)

        result = await self.db.execute(query)
        embeddings = result.scalars().all()

        for emb in embeddings:
            await self.db.delete(emb)
        await self.db.flush()

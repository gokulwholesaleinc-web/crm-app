"""AI-related models for RAG and conversations."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from src.database import Base


class AIEmbedding(Base):
    """
    Stores embeddings for RAG (Retrieval Augmented Generation).

    Uses pgvector for efficient similarity search.
    """
    __tablename__ = "ai_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Entity reference
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Content that was embedded
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), default="description")  # description, note, activity, etc.

    # Embedding vector (1536 dimensions for OpenAI text-embedding-3-small)
    embedding: Mapped[list] = mapped_column(Vector(1536))

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class AIConversation(Base):
    """Stores AI assistant conversation history."""
    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Conversation content
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Context (optional - for tracking what data was referenced)
    context_entities: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of entity refs

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Session tracking
    session_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)

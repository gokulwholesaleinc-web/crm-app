"""AI-related models for RAG and conversations."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, ForeignKey, Text, DateTime, Boolean, func, JSON
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


class AIFeedback(Base):
    """Stores user feedback on AI responses for learning."""
    __tablename__ = "ai_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    session_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_context_ids: Mapped[Optional[dict]] = mapped_column(JSON)

    # Feedback: positive, negative, correction
    feedback: Mapped[str] = mapped_column(String(20), nullable=False)
    correction_text: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class AIKnowledgeDocument(Base):
    """Stores uploaded knowledge base documents."""
    __tablename__ = "ai_knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class AILearning(Base):
    """Stores learned preferences and patterns per user."""
    __tablename__ = "ai_learnings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    times_reinforced: Mapped[int] = mapped_column(Integer, default=1)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class AIInteractionLog(Base):
    """Logs AI interactions for pattern analysis."""
    __tablename__ = "ai_interaction_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    response_quality: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    correction_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class AIActionLog(Base):
    """Audit log for every AI function execution."""
    __tablename__ = "ai_action_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    session_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    function_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    arguments: Mapped[Optional[dict]] = mapped_column(JSON)
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    was_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    model_used: Mapped[Optional[str]] = mapped_column(String(50))
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class AIUserPreferences(Base):
    """Stores user preferences for AI personalization."""
    __tablename__ = "ai_user_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    preferred_communication_style: Mapped[Optional[str]] = mapped_column(
        String(50), default="professional"
    )
    priority_entities: Mapped[Optional[dict]] = mapped_column(JSON)
    custom_instructions: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

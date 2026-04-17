"""Meta (Facebook/Instagram) integration models."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class CompanyMetaData(Base):
    """Stores Meta/Facebook page data for a company."""
    __tablename__ = "company_meta_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True)
    page_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    page_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    followers_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    likes_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Instagram fields
    instagram_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    instagram_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    instagram_followers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    instagram_media_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MetaCredential(Base):
    """Stores OAuth2 credentials for Meta (Facebook/Instagram) per user."""
    __tablename__ = "meta_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    page_access_tokens: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {page_id: token}
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MetaLeadCapture(Base):
    """Stores leads captured from Meta Lead Ads via webhooks."""
    __tablename__ = "meta_lead_captures"

    id: Mapped[int] = mapped_column(primary_key=True)
    form_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    leadgen_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    page_id: Mapped[str] = mapped_column(String(100), nullable=False)
    ad_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lead_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

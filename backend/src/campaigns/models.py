"""Campaign models for marketing campaigns."""

from datetime import date
from typing import Optional
from sqlalchemy import String, Integer, ForeignKey, Text, Date, Float, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base
from src.core.mixins.auditable import AuditableMixin


class Campaign(Base, AuditableMixin):
    """Marketing campaign model."""
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    campaign_type: Mapped[str] = mapped_column(String(50), nullable=False)  # email, event, webinar, ads, etc.

    # Status
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned, active, paused, completed

    # Dates
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)

    # Budget
    budget_amount: Mapped[Optional[float]] = mapped_column(Float)
    actual_cost: Mapped[Optional[float]] = mapped_column(Float)
    budget_currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Targets
    target_audience: Mapped[Optional[str]] = mapped_column(Text)
    expected_revenue: Mapped[Optional[float]] = mapped_column(Float)
    expected_response: Mapped[Optional[int]] = mapped_column(Integer)  # Expected number of responses

    # Results
    actual_revenue: Mapped[Optional[float]] = mapped_column(Float)
    num_sent: Mapped[int] = mapped_column(Integer, default=0)
    num_responses: Mapped[int] = mapped_column(Integer, default=0)
    num_converted: Mapped[int] = mapped_column(Integer, default=0)

    # Owner
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    # Relationships
    members: Mapped[list["CampaignMember"]] = relationship(
        "CampaignMember",
        back_populates="campaign",
        lazy="dynamic",
    )

    @property
    def response_rate(self) -> Optional[float]:
        """Calculate response rate percentage."""
        if self.num_sent and self.num_sent > 0:
            return (self.num_responses / self.num_sent) * 100
        return None

    @property
    def conversion_rate(self) -> Optional[float]:
        """Calculate conversion rate percentage."""
        if self.num_responses and self.num_responses > 0:
            return (self.num_converted / self.num_responses) * 100
        return None

    @property
    def roi(self) -> Optional[float]:
        """Calculate ROI percentage."""
        if self.actual_cost and self.actual_cost > 0 and self.actual_revenue:
            return ((self.actual_revenue - self.actual_cost) / self.actual_cost) * 100
        return None


class CampaignMember(Base):
    """Campaign member - links contacts/leads to campaigns."""
    __tablename__ = "campaign_members"

    id: Mapped[int] = mapped_column(primary_key=True)

    campaign_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Polymorphic link to contact or lead
    member_type: Mapped[str] = mapped_column(String(20), nullable=False)  # contact, lead
    member_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, sent, responded, converted

    # Tracking
    sent_at: Mapped[Optional[date]] = mapped_column(Date)
    responded_at: Mapped[Optional[date]] = mapped_column(Date)
    converted_at: Mapped[Optional[date]] = mapped_column(Date)

    # Response details
    response_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="members")

    __table_args__ = (
        Index("ix_campaign_members_campaign", "campaign_id"),
        Index("ix_campaign_members_member", "member_type", "member_id"),
    )

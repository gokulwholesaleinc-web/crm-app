"""Pydantic schemas for proposals."""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


# =============================================================================
# Proposal Schemas
# =============================================================================

class ProposalBase(BaseModel):
    title: str
    content: Optional[str] = None
    opportunity_id: Optional[int] = None
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    quote_id: Optional[int] = None
    status: str = "draft"
    cover_letter: Optional[str] = None
    executive_summary: Optional[str] = None
    scope_of_work: Optional[str] = None
    pricing_section: Optional[str] = None
    timeline: Optional[str] = None
    terms: Optional[str] = None
    valid_until: Optional[date] = None
    owner_id: Optional[int] = None


class ProposalCreate(ProposalBase):
    pass


class ProposalUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    opportunity_id: Optional[int] = None
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    quote_id: Optional[int] = None
    status: Optional[str] = None
    cover_letter: Optional[str] = None
    executive_summary: Optional[str] = None
    scope_of_work: Optional[str] = None
    pricing_section: Optional[str] = None
    timeline: Optional[str] = None
    terms: Optional[str] = None
    valid_until: Optional[date] = None
    owner_id: Optional[int] = None


class ContactBrief(BaseModel):
    id: int
    full_name: str

    model_config = ConfigDict(from_attributes=True)


class CompanyBrief(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class OpportunityBrief(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class QuoteBrief(BaseModel):
    id: int
    quote_number: str
    title: str
    total: float

    model_config = ConfigDict(from_attributes=True)


class ProposalViewResponse(BaseModel):
    id: int
    proposal_id: int
    viewed_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ProposalResponse(ProposalBase):
    id: int
    proposal_number: str
    view_count: int
    last_viewed_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    contact: Optional[ContactBrief] = None
    company: Optional[CompanyBrief] = None
    opportunity: Optional[OpportunityBrief] = None
    quote: Optional[QuoteBrief] = None

    model_config = ConfigDict(from_attributes=True)


class ProposalListResponse(BaseModel):
    items: List[ProposalResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ProposalPublicResponse(BaseModel):
    """Public view of a proposal (no auth required)."""
    proposal_number: str
    title: str
    content: Optional[str] = None
    cover_letter: Optional[str] = None
    executive_summary: Optional[str] = None
    scope_of_work: Optional[str] = None
    pricing_section: Optional[str] = None
    timeline: Optional[str] = None
    terms: Optional[str] = None
    valid_until: Optional[date] = None
    status: str
    company: Optional[CompanyBrief] = None
    contact: Optional[ContactBrief] = None

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# AI Generation Request
# =============================================================================

class AIGenerateRequest(BaseModel):
    opportunity_id: int


# =============================================================================
# Template Schemas
# =============================================================================

class ProposalTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    content_template: Optional[str] = None


class ProposalTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    content_template: Optional[str] = None


class ProposalTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    content_template: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

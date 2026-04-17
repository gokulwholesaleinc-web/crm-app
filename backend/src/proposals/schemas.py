"""Pydantic schemas for proposals."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

# Proposal Schemas

class ProposalBase(BaseModel):
    title: str
    content: str | None = None
    opportunity_id: int | None = None
    contact_id: int | None = None
    company_id: int | None = None
    quote_id: int | None = None
    status: str = "draft"
    cover_letter: str | None = None
    executive_summary: str | None = None
    scope_of_work: str | None = None
    pricing_section: str | None = None
    timeline: str | None = None
    terms: str | None = None
    valid_until: date | None = None
    designated_signer_email: str | None = None
    owner_id: int | None = None


class ProposalCreate(ProposalBase):
    pass


class ProposalUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    opportunity_id: int | None = None
    contact_id: int | None = None
    company_id: int | None = None
    quote_id: int | None = None
    cover_letter: str | None = None
    executive_summary: str | None = None
    scope_of_work: str | None = None
    pricing_section: str | None = None
    timeline: str | None = None
    terms: str | None = None
    valid_until: date | None = None
    designated_signer_email: str | None = None
    owner_id: int | None = None


class ProposalAcceptRequest(BaseModel):
    """E-signature payload submitted from the public accept page."""
    signer_name: str
    signer_email: str


class ProposalRejectRequest(BaseModel):
    reason: str | None = None


from src.core.schemas import CompanyBrief, ContactBrief, OpportunityBrief, QuoteBrief  # noqa: E402


class ProposalViewResponse(BaseModel):
    id: int
    proposal_id: int
    viewed_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProposalResponse(ProposalBase):
    id: int
    proposal_number: str
    view_count: int
    last_viewed_at: datetime | None = None
    sent_at: datetime | None = None
    viewed_at: datetime | None = None
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    signer_name: str | None = None
    signer_email: str | None = None
    signer_ip: str | None = None
    signer_user_agent: str | None = None
    signed_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    contact: ContactBrief | None = None
    company: CompanyBrief | None = None
    opportunity: OpportunityBrief | None = None
    quote: QuoteBrief | None = None

    model_config = ConfigDict(from_attributes=True)


class ProposalListResponse(BaseModel):
    items: list[ProposalResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ProposalBranding(BaseModel):
    """Tenant branding data for public proposal view."""
    company_name: str | None = None
    logo_url: str | None = None
    primary_color: str = "#6366f1"
    secondary_color: str = "#8b5cf6"
    accent_color: str = "#22c55e"
    footer_text: str | None = None


class ProposalPublicResponse(BaseModel):
    """Public view of a proposal (no auth required)."""
    proposal_number: str
    title: str
    content: str | None = None
    cover_letter: str | None = None
    executive_summary: str | None = None
    scope_of_work: str | None = None
    pricing_section: str | None = None
    timeline: str | None = None
    terms: str | None = None
    valid_until: date | None = None
    status: str
    company: CompanyBrief | None = None
    contact: ContactBrief | None = None
    branding: ProposalBranding | None = None

    model_config = ConfigDict(from_attributes=True)


class ProposalSendRequest(BaseModel):
    """Request to send a proposal with optional PDF attachment."""
    attach_pdf: bool = False


# AI Generation Request

class AIGenerateRequest(BaseModel):
    opportunity_id: int


# Template Schemas

class ProposalTemplateCreate(BaseModel):
    name: str
    body: str
    description: str | None = None
    legal_terms: str | None = None
    category: str | None = None
    is_default: bool = False


class ProposalTemplateUpdate(BaseModel):
    name: str | None = None
    body: str | None = None
    description: str | None = None
    legal_terms: str | None = None
    category: str | None = None
    is_default: bool | None = None


class ProposalTemplateResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    body: str
    legal_terms: str | None = None
    category: str | None = None
    is_default: bool
    owner_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreateFromTemplateRequest(BaseModel):
    template_id: int
    contact_id: int
    company_id: int | None = None
    custom_variables: dict | None = None

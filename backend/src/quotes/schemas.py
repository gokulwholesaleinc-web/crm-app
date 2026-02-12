"""Pydantic schemas for quotes."""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, model_validator


# =============================================================================
# Line Item Schemas
# =============================================================================

class QuoteLineItemCreate(BaseModel):
    description: str
    quantity: float = 1
    unit_price: float = 0
    discount: float = 0
    sort_order: int = 0


class QuoteLineItemResponse(BaseModel):
    id: int
    quote_id: int
    description: str
    quantity: float
    unit_price: float
    discount: float
    total: float
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Quote Schemas
# =============================================================================

class QuoteBase(BaseModel):
    title: str
    description: Optional[str] = None
    opportunity_id: Optional[int] = None
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    status: str = "draft"
    valid_until: Optional[date] = None
    currency: str = "USD"
    discount_type: Optional[str] = None
    discount_value: float = 0
    tax_rate: float = 0
    terms_and_conditions: Optional[str] = None
    notes: Optional[str] = None
    owner_id: Optional[int] = None
    payment_type: str = "one_time"
    recurring_interval: Optional[str] = None

    @model_validator(mode="after")
    def validate_recurring_interval(self):
        if self.payment_type == "subscription" and not self.recurring_interval:
            raise ValueError("recurring_interval is required for subscription quotes")
        if self.payment_type != "subscription":
            self.recurring_interval = None
        return self


class QuoteCreate(QuoteBase):
    line_items: Optional[List[QuoteLineItemCreate]] = None


class QuoteUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    opportunity_id: Optional[int] = None
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    status: Optional[str] = None
    valid_until: Optional[date] = None
    currency: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = None
    tax_rate: Optional[float] = None
    terms_and_conditions: Optional[str] = None
    notes: Optional[str] = None
    owner_id: Optional[int] = None
    payment_type: Optional[str] = None
    recurring_interval: Optional[str] = None


from src.core.schemas import ContactBrief, CompanyBrief, OpportunityBrief  # noqa: E402


class QuoteResponse(QuoteBase):
    id: int
    quote_number: str
    subtotal: float
    tax_amount: float
    total: float
    sent_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    signer_name: Optional[str] = None
    signer_email: Optional[str] = None
    signed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    line_items: List[QuoteLineItemResponse] = []
    contact: Optional[ContactBrief] = None
    company: Optional[CompanyBrief] = None
    opportunity: Optional[OpportunityBrief] = None

    model_config = ConfigDict(from_attributes=True)


class QuoteListResponse(BaseModel):
    items: List[QuoteResponse]
    total: int
    page: int
    page_size: int
    pages: int


# =============================================================================
# Public Quote View Schemas
# =============================================================================

class QuoteBranding(BaseModel):
    """Tenant branding data for public quote view."""
    company_name: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: str = "#6366f1"
    secondary_color: str = "#8b5cf6"
    accent_color: str = "#22c55e"
    footer_text: Optional[str] = None


class QuotePublicLineItem(BaseModel):
    """Line item for public quote view (no internal IDs exposed)."""
    description: str
    quantity: float
    unit_price: float
    discount: float
    total: float

    model_config = ConfigDict(from_attributes=True)


class QuotePublicResponse(BaseModel):
    """Public view of a quote (no auth required)."""
    quote_number: str
    title: str
    description: Optional[str] = None
    status: str
    currency: str = "USD"
    valid_until: Optional[date] = None
    subtotal: float = 0
    tax_amount: float = 0
    total: float = 0
    discount_type: Optional[str] = None
    discount_value: float = 0
    terms_and_conditions: Optional[str] = None
    payment_type: str = "one_time"
    recurring_interval: Optional[str] = None
    line_items: List[QuotePublicLineItem] = []
    contact: Optional[ContactBrief] = None
    company: Optional[CompanyBrief] = None
    branding: Optional[QuoteBranding] = None

    model_config = ConfigDict(from_attributes=True)


class QuoteAcceptRequest(BaseModel):
    """Request body for accepting a quote via public link (e-sign)."""
    signer_name: str
    signer_email: str


class QuoteRejectRequest(BaseModel):
    """Request body for rejecting a quote via public link."""
    reason: Optional[str] = None


# =============================================================================
# Template Schemas
# =============================================================================

class QuoteTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    default_terms: Optional[str] = None
    default_notes: Optional[str] = None
    line_items_template: Optional[dict] = None


class QuoteTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    default_terms: Optional[str] = None
    default_notes: Optional[str] = None
    line_items_template: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Product Bundle Schemas
# =============================================================================

class ProductBundleItemCreate(BaseModel):
    description: str
    quantity: float = 1
    unit_price: float = 0
    sort_order: int = 0


class ProductBundleItemResponse(BaseModel):
    id: int
    bundle_id: int
    description: str
    quantity: float
    unit_price: float
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ProductBundleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True
    items: Optional[List[ProductBundleItemCreate]] = None


class ProductBundleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    items: Optional[List[ProductBundleItemCreate]] = None


class ProductBundleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_active: bool
    items: List[ProductBundleItemResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductBundleListResponse(BaseModel):
    items: List[ProductBundleResponse]
    total: int
    page: int
    page_size: int
    pages: int

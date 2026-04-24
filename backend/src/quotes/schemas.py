"""Pydantic schemas for quotes."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator

# Line Item Schemas

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


# Quote Schemas

class QuoteBase(BaseModel):
    title: str
    description: str | None = None
    opportunity_id: int | None = None
    contact_id: int | None = None
    company_id: int | None = None
    status: str = "draft"
    valid_until: date | None = None
    currency: str = "USD"
    discount_type: str | None = None
    discount_value: float = 0
    tax_rate: float = 0
    terms_and_conditions: str | None = None
    notes: str | None = None
    owner_id: int | None = None
    payment_type: str = "one_time"
    recurring_interval: str | None = None  # 'month' | 'year'
    recurring_interval_count: int | None = None  # 1, 3 (quarterly), 6 (bi-yearly), ...
    designated_signer_email: str | None = None

    @model_validator(mode="after")
    def validate_recurring_interval(self):
        # Accept and translate legacy values ('monthly', 'quarterly',
        # 'yearly') that pre-date the Stripe-native ('month'|'year' +
        # count) split. New clients should send ('month', 1),
        # ('month', 3), ('month', 6), or ('year', 1) directly.
        _LEGACY = {
            "monthly": ("month", 1),
            "quarterly": ("month", 3),
            "bi_yearly": ("month", 6),
            "yearly": ("year", 1),
        }
        if self.payment_type == "subscription":
            if not self.recurring_interval:
                raise ValueError(
                    "recurring_interval is required for subscription quotes",
                )
            if self.recurring_interval in _LEGACY:
                legacy_interval, legacy_count = _LEGACY[self.recurring_interval]
                self.recurring_interval = legacy_interval
                if self.recurring_interval_count is None:
                    self.recurring_interval_count = legacy_count
            if self.recurring_interval not in ("month", "year"):
                raise ValueError(
                    "recurring_interval must be 'month' or 'year'",
                )
            if self.recurring_interval_count is None:
                self.recurring_interval_count = 1
            elif self.recurring_interval_count < 1:
                raise ValueError("recurring_interval_count must be >= 1")
        else:
            self.recurring_interval = None
            self.recurring_interval_count = None
        return self


class QuoteCreate(QuoteBase):
    line_items: list[QuoteLineItemCreate] | None = None


class QuoteUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    opportunity_id: int | None = None
    contact_id: int | None = None
    company_id: int | None = None
    valid_until: date | None = None
    currency: str | None = None
    discount_type: str | None = None
    discount_value: float | None = None
    tax_rate: float | None = None
    terms_and_conditions: str | None = None
    notes: str | None = None
    owner_id: int | None = None
    payment_type: str | None = None
    recurring_interval: str | None = None
    recurring_interval_count: int | None = None
    designated_signer_email: str | None = None


from src.core.schemas import CompanyBrief, ContactBrief, OpportunityBrief  # noqa: E402


class QuoteResponse(QuoteBase):
    id: int
    quote_number: str
    subtotal: float
    tax_amount: float
    total: float
    sent_at: datetime | None = None
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
    line_items: list[QuoteLineItemResponse] = []
    contact: ContactBrief | None = None
    company: CompanyBrief | None = None
    opportunity: OpportunityBrief | None = None

    model_config = ConfigDict(from_attributes=True)


class QuoteListResponse(BaseModel):
    items: list[QuoteResponse]
    total: int
    page: int
    page_size: int
    pages: int


# Public Quote View Schemas

class QuoteBranding(BaseModel):
    """Tenant branding data for public quote view."""
    company_name: str | None = None
    logo_url: str | None = None
    primary_color: str = "#6366f1"
    secondary_color: str = "#8b5cf6"
    accent_color: str = "#22c55e"
    footer_text: str | None = None


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
    description: str | None = None
    status: str
    currency: str = "USD"
    valid_until: date | None = None
    subtotal: float = 0
    tax_amount: float = 0
    total: float = 0
    discount_type: str | None = None
    discount_value: float = 0
    terms_and_conditions: str | None = None
    payment_type: str = "one_time"
    recurring_interval: str | None = None
    recurring_interval_count: int | None = None
    line_items: list[QuotePublicLineItem] = []
    contact: ContactBrief | None = None
    company: CompanyBrief | None = None
    branding: QuoteBranding | None = None

    model_config = ConfigDict(from_attributes=True)


class QuoteAcceptRequest(BaseModel):
    """Request body for accepting a quote via public link (e-sign)."""
    signer_name: str
    signer_email: str


class QuoteRejectRequest(BaseModel):
    """Request body for rejecting a quote via public link."""
    reason: str | None = None


# Template Schemas

class QuoteTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    default_terms: str | None = None
    default_notes: str | None = None
    line_items_template: dict | None = None


class QuoteTemplateResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    default_terms: str | None = None
    default_notes: str | None = None
    line_items_template: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Product Bundle Schemas

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
    description: str | None = None
    is_active: bool = True
    items: list[ProductBundleItemCreate] | None = None


class ProductBundleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    items: list[ProductBundleItemCreate] | None = None


class ProductBundleResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_active: bool
    items: list[ProductBundleItemResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductBundleListResponse(BaseModel):
    items: list[ProductBundleResponse]
    total: int
    page: int
    page_size: int
    pages: int

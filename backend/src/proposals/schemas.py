"""Pydantic schemas for proposals."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

PaymentType = Literal["one_time", "subscription"]
RecurringInterval = Literal["month", "year"]


class ProposalBillingMixin(BaseModel):
    """Structured pricing fields shared by ProposalBase/Update/Response.

    When payment_type='subscription', recurring_interval and
    recurring_interval_count must both be set. Validated at the Pydantic
    layer so the Stripe path never sees a half-configured subscription.
    """
    payment_type: PaymentType = "one_time"
    recurring_interval: RecurringInterval | None = None
    recurring_interval_count: int | None = None
    amount: Decimal | None = None
    currency: str = "USD"

    @model_validator(mode="after")
    def _check_recurring(self) -> "ProposalBillingMixin":
        if self.payment_type == "subscription":
            if not self.recurring_interval or not self.recurring_interval_count:
                raise ValueError(
                    "subscription proposals require recurring_interval and "
                    "recurring_interval_count",
                )
            if self.recurring_interval_count < 1:
                raise ValueError("recurring_interval_count must be >= 1")
        # one_time must not carry recurrence hints; reject so we don't
        # store contradictory state at the DB layer.
        elif self.recurring_interval is not None or self.recurring_interval_count is not None:
            raise ValueError(
                "one_time proposals must not set recurring_interval/count",
            )
        if self.amount is not None and self.amount <= 0:
            raise ValueError("amount must be > 0")
        return self


# Proposal Schemas

class ProposalBase(ProposalBillingMixin):
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
    payment_type: PaymentType | None = None
    recurring_interval: RecurringInterval | None = None
    recurring_interval_count: int | None = None
    amount: Decimal | None = None
    currency: str | None = None

    @model_validator(mode="after")
    def _check_billing_consistency(self) -> "ProposalUpdate":
        """Validate the subset of billing fields present in a PATCH.

        Partial updates pass this validator, but if any billing field is
        *explicitly* set, the combination still has to be internally
        consistent so we never land a half-configured subscription in
        the DB.
        """
        if self.payment_type == "subscription":
            # When turning a proposal into a subscription, interval + count
            # must land in the same PATCH (the service layer doesn't
            # merge-then-validate against the existing row).
            if not self.recurring_interval or not self.recurring_interval_count:
                raise ValueError(
                    "switching to subscription requires recurring_interval "
                    "and recurring_interval_count in the same update",
                )
            if self.recurring_interval_count < 1:
                raise ValueError("recurring_interval_count must be >= 1")
        elif self.payment_type == "one_time":
            if self.recurring_interval is not None or self.recurring_interval_count is not None:
                raise ValueError(
                    "one_time proposals must not set recurring_interval/count",
                )
        if self.amount is not None and self.amount <= 0:
            raise ValueError("amount must be > 0")
        return self


class ProposalAcceptRequest(BaseModel):
    """E-signature payload submitted from the public accept page."""
    signer_name: str
    signer_email: str


class ProposalRejectRequest(BaseModel):
    signer_email: str
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
    stripe_invoice_id: str | None = None
    stripe_subscription_id: str | None = None
    stripe_checkout_session_id: str | None = None
    stripe_payment_url: str | None = None
    invoice_sent_at: datetime | None = None
    paid_at: datetime | None = None
    billing_error: str | None = None
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
    privacy_policy_url: str | None = None
    terms_of_service_url: str | None = None


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
    payment_type: PaymentType = "one_time"
    recurring_interval: RecurringInterval | None = None
    recurring_interval_count: int | None = None
    amount: Decimal | None = None
    currency: str = "USD"
    # Payment URL is only populated after the client accepts and the
    # backend spawns a Stripe Invoice / Checkout Session. Surfaced here
    # so the public page can render a "Complete payment" CTA without a
    # second network round-trip.
    stripe_payment_url: str | None = None
    paid_at: datetime | None = None
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

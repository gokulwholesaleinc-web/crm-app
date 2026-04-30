"""Pydantic schemas for payments."""

import urllib.parse
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Stripe Customer Schemas

class StripeCustomerCreate(BaseModel):
    contact_id: int | None = None
    company_id: int | None = None
    email: str | None = None
    name: str | None = None


class StripeCustomerResponse(BaseModel):
    id: int
    contact_id: int | None = None
    company_id: int | None = None
    stripe_customer_id: str
    email: str | None = None
    name: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StripeCustomerListResponse(BaseModel):
    items: list[StripeCustomerResponse]
    total: int
    page: int
    page_size: int
    pages: int


class SyncCustomerRequest(BaseModel):
    contact_id: int | None = None
    company_id: int | None = None


# Product Schemas

class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    stripe_product_id: str | None = None
    is_active: bool = True


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    stripe_product_id: str | None = None
    is_active: bool | None = None


class PriceResponse(BaseModel):
    id: int
    product_id: int
    stripe_price_id: str | None = None
    amount: Decimal
    currency: str
    recurring_interval: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    stripe_product_id: str | None = None
    is_active: bool
    owner_id: int | None = None
    prices: list[PriceResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int
    pages: int


# Price Schemas

class PriceCreate(BaseModel):
    product_id: int
    amount: Decimal
    currency: str = "USD"
    recurring_interval: str | None = None
    stripe_price_id: str | None = None
    is_active: bool = True


# Payment Schemas

class PaymentBase(BaseModel):
    amount: Decimal
    currency: str = "USD"
    customer_id: int | None = None
    opportunity_id: int | None = None
    quote_id: int | None = None
    status: str = "pending"
    payment_method: str | None = None
    receipt_url: str | None = None
    owner_id: int | None = None


class PaymentCreate(PaymentBase):
    stripe_payment_intent_id: str | None = None
    stripe_checkout_session_id: str | None = None
    stripe_invoice_id: str | None = None


class PaymentUpdate(BaseModel):
    status: str | None = None
    payment_method: str | None = None
    receipt_url: str | None = None
    stripe_payment_intent_id: str | None = None
    stripe_checkout_session_id: str | None = None
    stripe_invoice_id: str | None = None


class CustomerBrief(BaseModel):
    id: int
    stripe_customer_id: str
    email: str | None = None
    name: str | None = None
    contact_id: int | None = None
    company_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class OpportunityBrief(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class QuoteBrief(BaseModel):
    id: int
    title: str

    model_config = ConfigDict(from_attributes=True)


class ProposalBrief(BaseModel):
    id: int
    title: str
    proposal_number: str

    model_config = ConfigDict(from_attributes=True)


class PaymentResponse(PaymentBase):
    id: int
    stripe_payment_intent_id: str | None = None
    stripe_checkout_session_id: str | None = None
    stripe_invoice_id: str | None = None
    created_at: datetime
    updated_at: datetime
    customer: CustomerBrief | None = None
    opportunity: OpportunityBrief | None = None
    quote: QuoteBrief | None = None
    # Proposals don't have a direct FK on Payment; resolved at serialization
    # time by matching stripe_invoice_id / stripe_checkout_session_id between
    # Payment and Proposal. None when the payment didn't originate from a
    # proposal e-sign accept.
    proposal: ProposalBrief | None = None

    model_config = ConfigDict(from_attributes=True)


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
    total: int
    page: int
    page_size: int
    pages: int


# Subscription Schemas

class SubscriptionResponse(BaseModel):
    id: int
    stripe_subscription_id: str
    customer_id: int
    price_id: int | None = None
    status: str
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool
    owner_id: int | None = None
    created_at: datetime
    updated_at: datetime
    customer: CustomerBrief | None = None
    price: PriceResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class SubscriptionListResponse(BaseModel):
    items: list[SubscriptionResponse]
    total: int
    page: int
    page_size: int
    pages: int


# Checkout / PaymentIntent Schemas

def _validate_url(v: str) -> str:
    """Validate that a URL has a proper http/https scheme."""
    parsed = urllib.parse.urlparse(v)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")
    if not parsed.netloc:
        raise ValueError("URL must have a valid hostname")
    return v


class CreateCheckoutRequest(BaseModel):
    quote_id: int | None = None
    amount: Decimal | None = None
    currency: str = "USD"
    success_url: str
    cancel_url: str
    customer_id: int | None = None

    @field_validator("success_url", "cancel_url")
    @classmethod
    def validate_urls(cls, v: str) -> str:
        return _validate_url(v)


class CreateCheckoutResponse(BaseModel):
    checkout_session_id: str
    checkout_url: str


class CreatePaymentIntentRequest(BaseModel):
    amount: Decimal
    currency: str = "USD"
    customer_id: int | None = None
    opportunity_id: int | None = None
    quote_id: int | None = None


class CreatePaymentIntentResponse(BaseModel):
    payment_intent_id: str
    client_secret: str
    payment_id: int


class CreateAndSendInvoiceRequest(BaseModel):
    customer_id: int
    amount: Decimal
    currency: str = "USD"
    description: str = "Invoice"
    due_days: int = Field(default=30, ge=1, le=365)
    quote_id: int | None = None
    payment_method_types: list[Literal["card", "us_bank_account"]] | None = None


class CreateAndSendInvoiceResponse(BaseModel):
    invoice_id: str
    payment_id: int
    status: str
    invoice_url: str | None = None


class CreateOnboardingLinkRequest(BaseModel):
    contact_id: int | None = None
    company_id: int | None = None
    success_url: str
    cancel_url: str

    @field_validator("success_url", "cancel_url")
    @classmethod
    def validate_urls(cls, v: str) -> str:
        return _validate_url(v)


class CreateOnboardingLinkResponse(BaseModel):
    url: str

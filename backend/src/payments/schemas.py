"""Pydantic schemas for payments."""

import urllib.parse
from datetime import datetime
from typing import Literal, Optional, List
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# Stripe Customer Schemas
# =============================================================================

class StripeCustomerCreate(BaseModel):
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    email: Optional[str] = None
    name: Optional[str] = None


class StripeCustomerResponse(BaseModel):
    id: int
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    stripe_customer_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StripeCustomerListResponse(BaseModel):
    items: List[StripeCustomerResponse]
    total: int
    page: int
    page_size: int
    pages: int


class SyncCustomerRequest(BaseModel):
    contact_id: Optional[int] = None
    company_id: Optional[int] = None


# =============================================================================
# Product Schemas
# =============================================================================

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    stripe_product_id: Optional[str] = None
    is_active: bool = True


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    stripe_product_id: Optional[str] = None
    is_active: Optional[bool] = None


class PriceResponse(BaseModel):
    id: int
    product_id: int
    stripe_price_id: Optional[str] = None
    amount: Decimal
    currency: str
    recurring_interval: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    stripe_product_id: Optional[str] = None
    is_active: bool
    owner_id: Optional[int] = None
    prices: List[PriceResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductListResponse(BaseModel):
    items: List[ProductResponse]
    total: int
    page: int
    page_size: int
    pages: int


# =============================================================================
# Price Schemas
# =============================================================================

class PriceCreate(BaseModel):
    product_id: int
    amount: Decimal
    currency: str = "USD"
    recurring_interval: Optional[str] = None
    stripe_price_id: Optional[str] = None
    is_active: bool = True


# =============================================================================
# Payment Schemas
# =============================================================================

class PaymentBase(BaseModel):
    amount: Decimal
    currency: str = "USD"
    customer_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    quote_id: Optional[int] = None
    status: str = "pending"
    payment_method: Optional[str] = None
    receipt_url: Optional[str] = None
    owner_id: Optional[int] = None


class PaymentCreate(PaymentBase):
    stripe_payment_intent_id: Optional[str] = None
    stripe_checkout_session_id: Optional[str] = None
    stripe_invoice_id: Optional[str] = None


class PaymentUpdate(BaseModel):
    status: Optional[str] = None
    payment_method: Optional[str] = None
    receipt_url: Optional[str] = None
    stripe_payment_intent_id: Optional[str] = None
    stripe_checkout_session_id: Optional[str] = None
    stripe_invoice_id: Optional[str] = None


class CustomerBrief(BaseModel):
    id: int
    stripe_customer_id: str
    email: Optional[str] = None
    name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class OpportunityBrief(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class QuoteBrief(BaseModel):
    id: int
    title: str

    model_config = ConfigDict(from_attributes=True)


class PaymentResponse(PaymentBase):
    id: int
    stripe_payment_intent_id: Optional[str] = None
    stripe_checkout_session_id: Optional[str] = None
    stripe_invoice_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    customer: Optional[CustomerBrief] = None
    opportunity: Optional[OpportunityBrief] = None
    quote: Optional[QuoteBrief] = None

    model_config = ConfigDict(from_attributes=True)


class PaymentListResponse(BaseModel):
    items: List[PaymentResponse]
    total: int
    page: int
    page_size: int
    pages: int


# =============================================================================
# Subscription Schemas
# =============================================================================

class SubscriptionResponse(BaseModel):
    id: int
    stripe_subscription_id: str
    customer_id: int
    price_id: int
    status: str
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool
    owner_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    customer: Optional[CustomerBrief] = None
    price: Optional[PriceResponse] = None

    model_config = ConfigDict(from_attributes=True)


class SubscriptionListResponse(BaseModel):
    items: List[SubscriptionResponse]
    total: int
    page: int
    page_size: int
    pages: int


# =============================================================================
# Checkout / PaymentIntent Schemas
# =============================================================================

def _validate_url(v: str) -> str:
    """Validate that a URL has a proper http/https scheme."""
    parsed = urllib.parse.urlparse(v)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")
    if not parsed.netloc:
        raise ValueError("URL must have a valid hostname")
    return v


class CreateCheckoutRequest(BaseModel):
    quote_id: Optional[int] = None
    amount: Optional[Decimal] = None
    currency: str = "USD"
    success_url: str
    cancel_url: str
    customer_id: Optional[int] = None

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
    customer_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    quote_id: Optional[int] = None


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
    quote_id: Optional[int] = None
    payment_method_types: Optional[List[Literal["card", "us_bank_account"]]] = None


class CreateAndSendInvoiceResponse(BaseModel):
    invoice_id: str
    payment_id: int
    status: str
    invoice_url: Optional[str] = None


class CreateOnboardingLinkRequest(BaseModel):
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    success_url: str
    cancel_url: str

    @field_validator("success_url", "cancel_url")
    @classmethod
    def validate_urls(cls, v: str) -> str:
        return _validate_url(v)


class CreateOnboardingLinkResponse(BaseModel):
    url: str

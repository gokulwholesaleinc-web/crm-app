"""Pydantic schemas for payments."""

from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


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


class PaymentUpdate(BaseModel):
    status: Optional[str] = None
    payment_method: Optional[str] = None
    receipt_url: Optional[str] = None
    stripe_payment_intent_id: Optional[str] = None
    stripe_checkout_session_id: Optional[str] = None


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

class CreateCheckoutRequest(BaseModel):
    quote_id: Optional[int] = None
    amount: Optional[Decimal] = None
    currency: str = "USD"
    success_url: str
    cancel_url: str
    customer_id: Optional[int] = None


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

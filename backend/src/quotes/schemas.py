"""Pydantic schemas for quotes."""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


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


class QuoteResponse(QuoteBase):
    id: int
    quote_number: str
    subtotal: float
    tax_amount: float
    total: float
    sent_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
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

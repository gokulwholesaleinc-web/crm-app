"""Pydantic schemas for companies."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from src.core.schemas import TagBrief


class CompanyBase(BaseModel):
    name: str
    website: str | None = None
    industry: str | None = None
    company_size: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    annual_revenue: int | None = None
    employee_count: int | None = None
    linkedin_url: str | None = None
    twitter_handle: str | None = None
    description: str | None = None
    link_creative_tier: str | None = None
    sow_url: str | None = None
    account_manager: str | None = None
    status: str = "prospect"
    segment: str | None = None
    owner_id: int | None = None


class CompanyCreate(CompanyBase):
    tag_ids: list[int] | None = None


class CompanyUpdate(BaseModel):
    name: str | None = None
    website: str | None = None
    industry: str | None = None
    company_size: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    annual_revenue: int | None = None
    employee_count: int | None = None
    linkedin_url: str | None = None
    twitter_handle: str | None = None
    description: str | None = None
    link_creative_tier: str | None = None
    sow_url: str | None = None
    account_manager: str | None = None
    status: str | None = None
    segment: str | None = None
    owner_id: int | None = None
    tag_ids: list[int] | None = None


class CompanyResponse(CompanyBase):
    id: int
    logo_url: str | None = None
    created_at: datetime
    updated_at: datetime
    tags: list[TagBrief] = []
    contact_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    total: int
    page: int
    page_size: int
    pages: int

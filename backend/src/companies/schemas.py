"""Pydantic schemas for companies."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, ConfigDict


class CompanyBase(BaseModel):
    name: str
    website: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    annual_revenue: Optional[int] = None
    employee_count: Optional[int] = None
    linkedin_url: Optional[str] = None
    twitter_handle: Optional[str] = None
    description: Optional[str] = None
    status: str = "prospect"
    owner_id: Optional[int] = None


class CompanyCreate(CompanyBase):
    tag_ids: Optional[List[int]] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    annual_revenue: Optional[int] = None
    employee_count: Optional[int] = None
    linkedin_url: Optional[str] = None
    twitter_handle: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    owner_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None


class TagBrief(BaseModel):
    id: int
    name: str
    color: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CompanyResponse(CompanyBase):
    id: int
    logo_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    tags: List[TagBrief] = []
    contact_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class CompanyListResponse(BaseModel):
    items: List[CompanyResponse]
    total: int
    page: int
    page_size: int
    pages: int

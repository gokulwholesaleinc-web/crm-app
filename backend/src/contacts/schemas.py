"""Pydantic schemas for contacts."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, ConfigDict
from src.core.schemas import TagBrief


class ContactBase(BaseModel):
    first_name: str
    last_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    company_id: Optional[int] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_handle: Optional[str] = None
    description: Optional[str] = None
    status: str = "active"
    owner_id: Optional[int] = None


class ContactCreate(ContactBase):
    tag_ids: Optional[List[int]] = None


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    company_id: Optional[int] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    linkedin_url: Optional[str] = None
    twitter_handle: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    owner_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None


class CompanyBrief(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class ContactResponse(ContactBase):
    id: int
    full_name: str
    avatar_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    company: Optional[CompanyBrief] = None
    tags: List[TagBrief] = []

    model_config = ConfigDict(from_attributes=True)


class ContactListResponse(BaseModel):
    items: List[ContactResponse]
    total: int
    page: int
    page_size: int
    pages: int

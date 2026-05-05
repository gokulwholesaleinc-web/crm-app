"""Pydantic schemas for contacts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from src.core.schemas import TagBrief


class ContactBase(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr | None = None
    phone: str | None = None
    mobile: str | None = None
    job_title: str | None = None
    department: str | None = None
    company_id: int | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    twitter_handle: str | None = None
    description: str | None = None
    status: str = "active"
    owner_id: int | None = None
    sales_code: str | None = None


class ContactCreate(ContactBase):
    tag_ids: list[int] | None = None


class ContactUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    mobile: str | None = None
    job_title: str | None = None
    department: str | None = None
    company_id: int | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    twitter_handle: str | None = None
    description: str | None = None
    status: str | None = None
    owner_id: int | None = None
    sales_code: str | None = None
    tag_ids: list[int] | None = None


class CompanyBrief(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class ContactResponse(ContactBase):
    id: int
    full_name: str
    avatar_url: str | None = None
    created_at: datetime
    updated_at: datetime
    company: CompanyBrief | None = None
    tags: list[TagBrief] = []

    model_config = ConfigDict(from_attributes=True)


class ContactListResponse(BaseModel):
    items: list[ContactResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ContactEmailAliasCreate(BaseModel):
    email: EmailStr
    label: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.strip().lower()


class ContactEmailAliasResponse(BaseModel):
    id: int
    contact_id: int
    email: str
    label: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

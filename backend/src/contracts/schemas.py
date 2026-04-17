"""Pydantic schemas for contracts."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ContractCreate(BaseModel):
    title: str
    contact_id: int | None = None
    company_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    scope: str | None = None
    value: float | None = None
    currency: str = "USD"
    status: str = "draft"
    owner_id: int | None = None


class ContractUpdate(BaseModel):
    title: str | None = None
    contact_id: int | None = None
    company_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    scope: str | None = None
    value: float | None = None
    currency: str | None = None
    status: str | None = None
    owner_id: int | None = None


class ContactBrief(BaseModel):
    id: int
    full_name: str

    model_config = ConfigDict(from_attributes=True)


class CompanyBrief(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class ContractResponse(BaseModel):
    id: int
    title: str
    contact_id: int | None = None
    company_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    scope: str | None = None
    value: float | None = None
    currency: str = "USD"
    status: str = "draft"
    owner_id: int | None = None
    created_at: datetime
    updated_at: datetime
    contact: ContactBrief | None = None
    company: CompanyBrief | None = None

    model_config = ConfigDict(from_attributes=True)


class ContractListResponse(BaseModel):
    items: list[ContractResponse]
    total: int
    page: int
    page_size: int
    pages: int

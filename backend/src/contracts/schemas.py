"""Pydantic schemas for contracts."""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class ContractCreate(BaseModel):
    title: str
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    scope: Optional[str] = None
    value: Optional[float] = None
    currency: str = "USD"
    status: str = "draft"
    owner_id: Optional[int] = None


class ContractUpdate(BaseModel):
    title: Optional[str] = None
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    scope: Optional[str] = None
    value: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    owner_id: Optional[int] = None


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
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    scope: Optional[str] = None
    value: Optional[float] = None
    currency: str = "USD"
    status: str = "draft"
    owner_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    contact: Optional[ContactBrief] = None
    company: Optional[CompanyBrief] = None

    model_config = ConfigDict(from_attributes=True)


class ContractListResponse(BaseModel):
    items: List[ContractResponse]
    total: int
    page: int
    page_size: int
    pages: int

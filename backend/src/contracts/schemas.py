"""Pydantic schemas for contracts."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


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
    # E-sign state — surfaced so the detail page can render Send/Sign actions.
    sent_at: datetime | None = None
    signed_at: datetime | None = None
    signed_by_name: str | None = None
    signed_pdf_r2_key: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ContractListResponse(BaseModel):
    items: list[ContractResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ---------- E-sign workflow ----------


class ContractSendRequest(BaseModel):
    """Request body for POST /api/contracts/{id}/send.

    All fields optional — the service uses contact email + tenant default
    template when the request is empty.
    """
    to_email: str | None = None
    message: str | None = None


class ContractSendResponse(BaseModel):
    """Returned after a contract is queued for the signer."""
    id: int
    status: str
    sent_at: datetime
    sign_url: str
    sign_token_expires_at: datetime


class ContractPublicView(BaseModel):
    """Public, signer-facing projection — no internal fields."""
    id: int
    title: str
    scope: str | None = None
    value: float | None = None
    currency: str = "USD"
    start_date: date | None = None
    end_date: date | None = None
    status: str
    company_name: str | None = None
    contact_name: str | None = None
    signer_email: str | None = None
    expires_at: datetime | None = None
    signed_at: datetime | None = None
    signed_by_name: str | None = None
    # Tenant branding for the public page.
    branding: dict = Field(default_factory=dict)


class ContractSignRequest(BaseModel):
    """Body for POST /api/contracts/public/{token}/sign."""
    signer_name: str = Field(min_length=1, max_length=255)
    signer_email: str = Field(min_length=3, max_length=255)
    signature_data_url: str = Field(min_length=1)


class ContractSignResponse(BaseModel):
    id: int
    status: str
    signed_at: datetime
    signed_by_name: str

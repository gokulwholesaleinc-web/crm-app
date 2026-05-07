"""Pydantic schemas for contracts."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# Status taxonomy (mirrors models.py docstring). Wrapping the public-
# facing schemas in a Literal stops API callers from POSTing arbitrary
# strings like `status="signed"` to fabricate a row that the auto-flip
# job and reports widgets then treat as legitimate.
ContractStatus = Literal[
    "draft", "sent", "signed", "active", "expired", "terminated",
]


class ContractCreate(BaseModel):
    title: str
    contact_id: int | None = None
    company_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    scope: str | None = None
    value: float | None = None
    currency: str = "USD"
    status: ContractStatus = "draft"
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
    status: ContractStatus | None = None
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
    # EmailStr catches typos before they reach the queue, where a bad
    # address otherwise just lands in the retry pile and the operator
    # silently believes the contract was delivered.
    to_email: EmailStr | None = None
    message: str | None = None


class ContractSendResponse(BaseModel):
    """Returned after a contract is queued for the signer.

    `sent_at` and `sign_token_expires_at` are nullable to match the
    underlying nullable ORM columns even though they should always be
    populated by the time the response renders — this keeps the schema
    honest with pyright.
    """
    id: int
    status: str
    sent_at: datetime | None = None
    sign_url: str
    sign_token_expires_at: datetime | None = None


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
    signer_email: EmailStr
    # Cap the signature-image data URL so a token-bearing client can't
    # grow the contracts table arbitrarily. ~200 KB is well above the
    # canvas's typical 20–50 KB PNG output.
    signature_data_url: str = Field(min_length=1, max_length=200_000)


class ContractSignResponse(BaseModel):
    id: int
    status: str
    # Nullable to match nullable ORM columns; pyright-honest.
    signed_at: datetime | None = None
    signed_by_name: str | None = None

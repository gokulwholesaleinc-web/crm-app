"""Pydantic schemas for onboarding packets (Phase 2).

Response models deliberately omit every token and the raw recipient e-mail
(PII): ``access_url`` appears ONLY on the create response (the one-time raw
link), ``recipient_email`` is masked, and ``field_values`` are never exposed
to staff. The public schemas split pre-gate (no session) vs post-gate (valid
``X-Onboarding-Session``).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# --------------------------------------------------------------------------
# Staff request/response
# --------------------------------------------------------------------------


class PacketCreate(BaseModel):
    contact_id: int
    recipient_email: EmailStr
    recipient_name: str | None = Field(default=None, max_length=255)
    company_id: int | None = None
    proposal_id: int | None = None
    template_ids: list[int] = Field(min_length=1)
    requires_esign_override: bool | None = None


class PacketDocumentSummary(BaseModel):
    """Per-document staff view — NO field_values (avoid PII surface)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    display_order: int
    original_filename: str
    requires_esign: bool
    attachment_id: int | None
    completed_at: datetime | None
    filled_pdf_error: str | None


class PacketDelivery(BaseModel):
    """Live e-mail delivery status for a packet (from EmailQueue rows)."""

    id: int
    to_email: str
    subject: str
    status: str
    created_at: datetime | None = None


class PacketResponse(BaseModel):
    """Staff packet view. Tokens are never echoed; recipient_email is masked.

    ``access_url`` is populated ONLY on the create response (the single time
    the raw access token is exposed) and is None on every read.
    """

    id: int
    contact_id: int
    company_id: int | None
    proposal_id: int | None
    status: str
    recipient_email_masked: str
    recipient_name: str | None
    document_count: int
    token_expires_at: datetime
    completed_at: datetime | None
    first_opened_at: datetime | None
    created_at: datetime
    documents: list[PacketDocumentSummary] = Field(default_factory=list)
    # Live EmailQueue delivery rows tagged to this packet (staff visibility);
    # named ``emails`` to match the frontend OnboardingPacketEmail[] contract.
    emails: list[PacketDelivery] = Field(default_factory=list)
    access_url: str | None = None


class SelectionResponse(BaseModel):
    """One proposal→onboarding-template selection row (staff view, §4.7)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    proposal_id: int
    template_id: int
    display_order: int


class SelectionSet(BaseModel):
    """Replace the whole ordered selection list for a proposal."""

    template_ids: list[int] = Field(default_factory=list)


class SelectionReorder(BaseModel):
    """Reassign display_order from a permutation of the current selection ids."""

    ordered_ids: list[int] = Field(default_factory=list)


class ResendResult(BaseModel):
    resent: list[str]


class PurgeResult(BaseModel):
    purged: bool


# --------------------------------------------------------------------------
# Public request/response
# --------------------------------------------------------------------------


class VerifyRequest(BaseModel):
    email: EmailStr


class VerifyResponse(BaseModel):
    # Generic by design — no enumeration. ``session_token`` is None on failure.
    success: bool
    session_token: str | None = None
    expires_in: int | None = None


class PublicBranding(BaseModel):
    """Sender-brand styling for the public onboarding page.

    Resolved from the (single-tenant) ``TenantSettings`` row so the public
    page renders the provider's logo/colours/footer instead of the generic
    indigo fallback. Field names + defaults mirror the frontend
    ``OnboardingPublicBranding`` contract exactly.
    """

    company_name: str | None = None
    logo_url: str | None = None
    primary_color: str = "#6366f1"
    secondary_color: str = "#8b5cf6"
    accent_color: str = "#22c55e"
    bg_color_light: str = "#f9fafb"
    surface_color_light: str = "#ffffff"
    footer_text: str | None = None
    privacy_policy_url: str | None = None
    terms_of_service_url: str | None = None


class PublicDocument(BaseModel):
    id: int
    original_filename: str
    field_definitions: list[dict]
    field_values: dict
    field_values_version: int
    requires_esign: bool


class PublicPacketPreResponse(BaseModel):
    """Pre-gate (no/invalid session): branding + counts only, no PII."""

    status: str
    document_count: int
    requires_email_verification: bool = True
    status_message: str
    company_name: str | None = None
    branding: PublicBranding | None = None


class PublicPacketPostResponse(BaseModel):
    """Post-gate (valid session): documents + disclosure + signature state."""

    status: str
    document_count: int
    status_message: str
    company_name: str | None = None
    branding: PublicBranding | None = None
    documents: list[PublicDocument] = Field(default_factory=list)
    signature_version: int = 0
    # True once the recipient has drawn a signature this packet — lets a
    # returning signer skip redrawing (the FE pre-marks it saved on reload).
    has_signature: bool = False
    # True once every e-sign doc has recorded electronic-records consent (the
    # affirmative /consent step) — lets a returning signer skip re-consenting,
    # and the fill page gate the signature pad on it. ``all()`` over an empty
    # esign set is True, so a non-esign packet reads as already-consented.
    has_consented: bool = False
    esign_disclosure: str | None = None
    esign_disclosure_version: str | None = None
    download_url: str | None = None


class DocumentPatch(BaseModel):
    field_values: dict
    base_version: int


class PatchResult(BaseModel):
    field_values_version: int


class SignatureSet(BaseModel):
    signature_png_base64: str
    base_signature_version: int


class SignatureResult(BaseModel):
    signature_version: int


class ConsentRequest(BaseModel):
    """E-records consent affirmation (§D.1).

    ``disclosure_version`` is the version the client actually rendered; when
    provided it is checked against the stored per-doc snapshot version (409 on
    mismatch). Omit it to skip the echo check.
    """

    disclosure_version: str | None = None


class ConsentResult(BaseModel):
    consented: bool
    documents_consented: int


class CompleteResponse(BaseModel):
    status: str
    download_url: str | None = None


# --------------------------------------------------------------------------
# Completion download (no login)
# --------------------------------------------------------------------------


class DownloadDocument(BaseModel):
    doc_id: int
    title: str
    url: str


class DownloadLandingResponse(BaseModel):
    documents: list[DownloadDocument]

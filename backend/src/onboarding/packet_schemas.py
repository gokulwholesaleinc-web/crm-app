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
    # When True the manual send emails the invite to the recipient (from the
    # creating staff's connected Gmail) — the route pre-flights Gmail BEFORE
    # minting and commits the token BEFORE queuing (F3/F4). When False the
    # packet is minted and the one-time ``access_url`` is returned to copy
    # without any email (the copy-link-only secondary path). Defaults False so
    # the create contract stays backward-compatible; the UI opts in per action.
    send_email: bool = False


class RegenerateLinkRequest(BaseModel):
    """Body for the copy-only link-regenerate action (F5/D1).

    Rotates the access token (the previously shared link dies) and returns the
    NEW raw ``access_url`` for staff to copy after a refresh lost the original.
    ``send_email`` (default False) optionally also re-queues the invite — only
    then is the owner's Gmail pre-flighted, since copying the link in-hand
    strands nobody.
    """

    send_email: bool = False


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


class PacketUpload(BaseModel):
    """One client-uploaded file on the packet (staff detail view, D5/F7).

    Carries the packet/doc/field correlation an ``AttachmentResponse`` drops
    (the contact-Attachments view exposes only filename/category). ``token_hash``
    + ``content_sha256`` are internal and never surfaced. The file itself is a
    ``contacts`` Attachment — download it via ``attachment_id``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    packet_document_id: int
    field_id: str
    attachment_id: int | None
    original_filename: str
    byte_size: int
    mime_type: str
    sensitive: bool
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
    # Client-uploaded files (D5) — populated ONLY on the single-packet detail
    # (GET /packets/{id}); the list endpoint leaves it empty to avoid an N+1.
    uploads: list[PacketUpload] = Field(default_factory=list)
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


class SecretValue(BaseModel):
    """One decrypted sensitive answer (owner/admin-only staff read, §F #1)."""

    field_id: str
    label: str | None = None
    value: str


class SecretValuesResponse(BaseModel):
    """Decrypted sensitive answers for one packet document (owner/admin only)."""

    document_id: int
    values: list[SecretValue] = Field(default_factory=list)


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
    # v3 kind discriminator — the fill page branches on this (esign_pdf → pdf.js
    # canvas; questionnaire/upload_request → the form renderer).
    kind: str
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


class ViewedResult(BaseModel):
    """Result of the kind-agnostic ``POST /viewed`` mark (P0-4).

    ``opened`` is True iff this call was the FIRST view under this access token
    (the active→opened transition fired); idempotent repeat calls return False.
    """

    viewed: bool = True
    opened: bool = False


class FileUploadResult(BaseModel):
    """Result of a fill-time file upload (``POST /documents/{id}/files``, P0-6).

    ``field_uploads`` is the full id list now stored in
    ``field_values[field_id]`` so the FE can re-render the field's file list
    without a refetch. No token / storage-path / sensitive ciphertext is
    exposed.
    """

    upload_id: int
    field_id: str
    original_filename: str
    byte_size: int
    mime_type: str
    field_uploads: list[int] = Field(default_factory=list)


class FileDeleteResult(BaseModel):
    """Result of deleting one uploaded file (``DELETE .../files/{upload_id}``)."""

    deleted: bool = True
    field_id: str
    field_uploads: list[int] = Field(default_factory=list)


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

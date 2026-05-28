"""Pydantic schemas for proposals."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
)

PaymentType = Literal["one_time", "subscription"]
RecurringInterval = Literal["month", "year"]


class SignatureFieldCoords(BaseModel):
    """Visual signature placement on a master service-agreement PDF.

    Coordinates are PDF points (origin = bottom-left), matching the
    reportlab/pypdf convention the stamper draws in. ``page`` is
    1-indexed so the picker UI's "Page N of M" label round-trips
    cleanly; the service layer converts to 0-indexed before handing
    off to ``pdf_stamper``.

    Garbage payloads 422 here so the operator gets a clear validation
    error instead of a silent fallback to the auto-box at stamp time.
    The stamper's clamp + auto-box guards still run as a second line
    of defense for fractional/page-out-of-range edge cases that survive
    validation (e.g. a box drawn slightly past the page edge).
    """

    # Keep in sync with
    # frontend/src/features/proposals/signaturePlacements.ts::isSignatureFieldCoords.
    # ``allow_inf_nan=False`` keeps inf/-inf/NaN from sneaking past the
    # ``ge=0`` / ``gt=0`` short-circuits and persisting as garbage that
    # only the stamper's clamp logic would catch.
    page: int = Field(ge=1)
    x: float = Field(ge=0, allow_inf_nan=False)
    y: float = Field(ge=0, allow_inf_nan=False)
    w: float = Field(gt=0, allow_inf_nan=False)
    h: float = Field(gt=0, allow_inf_nan=False)


SignatureFieldPlacementList: TypeAlias = Annotated[
    list[SignatureFieldCoords],
    Field(min_length=1, max_length=100),
]
SignatureFieldPlacementValue: TypeAlias = SignatureFieldCoords | SignatureFieldPlacementList
SignatureFieldPlacementWriteValue: TypeAlias = SignatureFieldPlacementList


class ProposalSigningDocumentResponse(BaseModel):
    """Staff-safe metadata for a PDF that receives the signer signature."""

    id: int
    proposal_id: int
    original_filename: str
    file_size: int
    content_type: str
    signature_field_coords: SignatureFieldPlacementValue | None = None
    date_field_coords: SignatureFieldPlacementValue | None = None
    signed_pdf_path: str | None = None
    signed_pdf_error: str | None = None
    display_order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProposalSigningDocumentUpdate(BaseModel):
    signature_field_coords: SignatureFieldPlacementWriteValue | None = None
    date_field_coords: SignatureFieldPlacementWriteValue | None = None


class ProposalBillingFields(BaseModel):
    """Legacy structured payment fields kept on read responses only.

    Proposal create/edit stopped accepting these values in May 2026. The
    columns remain so old records, payment retry paths, and public
    awaiting-payment links keep working without showing billing controls in
    proposal composition.
    """

    payment_type: PaymentType = "one_time"
    recurring_interval: RecurringInterval | None = None
    recurring_interval_count: int | None = None
    amount: Decimal | None = None
    currency: str = "USD"


# Proposal Schemas


class ProposalBase(BaseModel):
    title: str
    content: str | None = None
    opportunity_id: int | None = None
    contact_id: int | None = None
    company_id: int | None = None
    quote_id: int | None = None
    status: str = "draft"
    cover_letter: str | None = None
    executive_summary: str | None = None
    scope_of_work: str | None = None
    pricing_section: str | None = None
    timeline: str | None = None
    terms: str | None = None
    valid_until: date | None = None
    designated_signer_email: str | None = None
    owner_id: int | None = None
    # Per-proposal T&C override. NULL → tenant default applies.
    terms_and_conditions: str | None = None

    model_config = ConfigDict(extra="forbid")


class ProposalCreate(ProposalBase):
    pass


class ProposalUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    opportunity_id: int | None = None
    contact_id: int | None = None
    company_id: int | None = None
    quote_id: int | None = None
    cover_letter: str | None = None
    executive_summary: str | None = None
    scope_of_work: str | None = None
    pricing_section: str | None = None
    timeline: str | None = None
    terms: str | None = None
    valid_until: date | None = None
    designated_signer_email: str | None = None
    owner_id: int | None = None
    terms_and_conditions: str | None = None
    # Visual signature placement. ``None`` (explicitly) clears the row
    # back to auto-box. New writes must be lists; read schemas still accept
    # one legacy box so old rows round-trip safely.
    signature_field_coords: SignatureFieldPlacementWriteValue | None = None
    date_field_coords: SignatureFieldPlacementWriteValue | None = None

    model_config = ConfigDict(extra="forbid")


class ProposalAcceptRequest(BaseModel):
    """E-signature payload submitted from the public Sign-to-Confirm modal.

    ``signature_image`` is the base64-encoded PNG drawn on the canvas
    (``data:image/png;base64,...`` form is accepted; the data-URL prefix
    is stripped server-side). The signer's email must match the
    proposal's designated recipient and the ESIGN consent box must
    have been ticked — both enforced by the service layer.
    """

    signer_name: str
    signer_email: EmailStr
    signature_image: str = Field(min_length=1, max_length=400_000)
    agreed_to_terms: bool
    signer_timezone: str | None = Field(default=None, max_length=100)
    selected_proposal_id: int | None = None


class ProposalRejectRequest(BaseModel):
    signer_email: EmailStr
    reason: str | None = None


class ProposalBundleCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    proposal_ids: list[int] = Field(min_length=2)

    model_config = ConfigDict(extra="forbid")


class ProposalBundleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    # Dissolve is handled by the dedicated DELETE option endpoint, not by
    # shrinking proposal_ids to a single id — keep the 2-min guard so the
    # PATCH router response shape stays a non-null bundle.
    proposal_ids: list[int] | None = Field(default=None, min_length=2)
    # Recommended-option control:
    # - field absent:        leave recommendation as-is (current default)
    # - integer:             mark THAT proposal recommended, others cleared
    # - explicit null:       clear all recommendations (no "Recommended" badge)
    # Cannot use `int | None` alone because pydantic-v2 still distinguishes
    # "not provided" from "explicitly null" via model_fields_set, which the
    # service consults to apply the right semantic.
    recommended_proposal_id: int | None = Field(default=None)

    model_config = ConfigDict(extra="forbid")


from src.core.schemas import (  # noqa: E402
    CompanyBrief,
    ContactBrief,
    ContactBriefWithEmail,
    OpportunityBrief,
    UserBrief,
)


class ProposalViewResponse(BaseModel):
    id: int
    proposal_id: int
    viewed_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProposalBundleBrief(BaseModel):
    id: int
    bundle_number: str
    public_token: str | None = None
    title: str
    description: str | None = None
    status: str
    selected_proposal_id: int | None = None
    selected_at: datetime | None = None
    sent_at: datetime | None = None
    accepted_at: datetime | None = None
    contact: ContactBrief | None = None
    company: CompanyBrief | None = None
    # Total option count — exposed so the list page can render a "N options"
    # badge without having to load every sub-proposal payload. Computed
    # from the SQLAlchemy `proposals` relationship via the
    # `proposals_count` @property on the ProposalBundle model.
    proposals_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class ProposalResponse(ProposalBase, ProposalBillingFields):
    id: int
    proposal_number: str
    # Unguessable token used to build the public /proposals/public/{token}
    # URL. The frontend's "Copy Link" button reads this off the detail
    # response; omitting it made every copy fall through to the
    # "no public link" error after the first page load.
    public_token: str | None = None
    view_count: int
    last_viewed_at: datetime | None = None
    sent_at: datetime | None = None
    viewed_at: datetime | None = None
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    signer_name: str | None = None
    signer_email: str | None = None
    signer_ip: str | None = None
    signer_user_agent: str | None = None
    signed_at: datetime | None = None
    agreed_to_terms_at: datetime | None = None
    terms_and_conditions_snapshot: str | None = None
    esign_disclosure_snapshot: str | None = None
    esign_disclosure_version: str | None = None
    acceptance_method: str | None = None
    rejection_reason: str | None = None
    stripe_invoice_id: str | None = None
    stripe_subscription_id: str | None = None
    stripe_checkout_session_id: str | None = None
    stripe_payment_url: str | None = None
    invoice_sent_at: datetime | None = None
    paid_at: datetime | None = None
    billing_error: str | None = None
    # Sign-to-Confirm artifacts. The drawn PNG itself is not surfaced
    # over the wire (it's stamped onto the signed PDF + rendered into
    # the audit page); the CRM UI checks ``signed_pdf_path`` to know
    # whether a downloadable countersigned copy exists.
    master_contract_pdf_path: str | None = None
    signed_pdf_path: str | None = None
    signed_pdf_error: str | None = None
    # Visual signature/date placement on the master contract PDF. Legacy
    # rows may contain one object; new saves contain a list of boxes.
    signature_field_coords: SignatureFieldPlacementValue | None = None
    date_field_coords: SignatureFieldPlacementValue | None = None
    signing_documents: list[ProposalSigningDocumentResponse] = []
    proposal_bundle_id: int | None = None
    bundle_sort_order: int = 0
    bundle_is_recommended: bool = False
    bundle: ProposalBundleBrief | None = None
    terms_and_conditions: str | None = None
    created_at: datetime
    updated_at: datetime
    contact: ContactBriefWithEmail | None = None
    company: CompanyBrief | None = None
    opportunity: OpportunityBrief | None = None
    # ``quote`` field removed 2026-05-14 — relationship dropped with the
    # quotes router unmount; ``quote_id`` column still present below.
    # ORM attr is `created_by_user`; JSON name is `created_by`.
    created_by: UserBrief | None = Field(
        default=None,
        validation_alias=AliasChoices("created_by", "created_by_user"),
    )
    owner: UserBrief | None = None
    # Per-view audit trail: every public-link GET appends a row with
    # IP + user-agent + timestamp. Surfaced on the detail response so
    # the CRM can show "viewed 12 times from 3 IPs" + the raw log for
    # forensics, dispute resolution, and legal discovery.
    views: list[ProposalViewResponse] = []

    model_config = ConfigDict(from_attributes=True)


class ProposalBundleResponse(ProposalBundleBrief):
    proposals: list[ProposalResponse] = []
    created_at: datetime
    updated_at: datetime
    created_by: UserBrief | None = Field(
        default=None,
        validation_alias=AliasChoices("created_by", "created_by_user"),
    )
    owner: UserBrief | None = None

    model_config = ConfigDict(from_attributes=True)


class ProposalListResponse(BaseModel):
    items: list[ProposalResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ProposalAttachmentPublicItem(BaseModel):
    """One attachment exposed on the public proposal view.

    ``viewed`` is per-token: it tracks whether this specific public link
    has already been used to download the file. The signer must view
    every attachment before they're allowed to accept.
    """

    id: int
    filename: str
    file_size: int
    mime_type: str
    viewed: bool = False

    model_config = ConfigDict(from_attributes=True)


class ProposalSigningDocumentPublicItem(BaseModel):
    """One signable PDF exposed on the public proposal view."""

    id: int
    filename: str
    file_size: int
    viewed: bool = False

    model_config = ConfigDict(from_attributes=True)


class ProposalBranding(BaseModel):
    """Tenant branding data for public proposal view."""

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


class ProposalPublicResponse(BaseModel):
    """Public view of a proposal (no auth required)."""

    id: int | None = None
    proposal_number: str
    public_token: str | None = None
    title: str
    content: str | None = None
    cover_letter: str | None = None
    executive_summary: str | None = None
    scope_of_work: str | None = None
    pricing_section: str | None = None
    timeline: str | None = None
    terms: str | None = None
    valid_until: date | None = None
    status: str
    # Legacy public payment compatibility. New proposal composition does not
    # expose billing controls, but old awaiting-payment links still need a
    # payment URL so customers can complete an already-issued payment flow.
    payment_type: PaymentType | None = None
    recurring_interval: RecurringInterval | None = None
    recurring_interval_count: int | None = None
    amount: Decimal | None = None
    currency: str | None = None
    stripe_payment_url: str | None = None
    paid_at: datetime | None = None
    proposal_bundle_id: int | None = None
    bundle_sort_order: int = 0
    bundle_is_recommended: bool = False
    bundle_id: int | None = None
    bundle_title: str | None = None
    bundle_description: str | None = None
    bundle_selected_proposal_id: int | None = None
    proposal_options: list["ProposalPublicResponse"] = []
    company: CompanyBrief | None = None
    contact: ContactBrief | None = None
    branding: ProposalBranding | None = None
    # Public-side attachment list. Customers must open every proposal
    # document before the public accept endpoint allows signing.
    attachments: list[ProposalAttachmentPublicItem] = []
    # Resolved T&C body for the Sign-to-Confirm modal — proposal
    # override if set, else tenant default. NULL = no T&C card.
    terms_and_conditions: str | None = None
    # Designated signer's email, pre-filled (and locked) in the modal.
    designated_signer_email: str | None = None
    # When true, the accept endpoint stamps the drawn signature onto
    # the master PDF and returns a downloadable countersigned copy.
    has_master_contract: bool = False
    signing_document_count: int = 0
    # Full ESIGN disclosure rendered on the public page; persisted verbatim
    # at accept so the stored evidence matches what the signer saw.
    esign_disclosure: str | None = None
    esign_disclosure_version: str | None = None
    signing_documents: list[ProposalSigningDocumentPublicItem] = Field(
        default_factory=list,
        validation_alias=AliasChoices("public_signing_documents"),
    )

    model_config = ConfigDict(from_attributes=True)


class ProposalSendRequest(BaseModel):
    """Request to send a proposal with optional PDF attachment."""

    attach_pdf: bool = False


# Template Schemas


class ProposalTemplateCreate(BaseModel):
    name: str
    body: str
    description: str | None = None
    legal_terms: str | None = None
    category: str | None = None
    is_default: bool = False


class ProposalTemplateUpdate(BaseModel):
    name: str | None = None
    body: str | None = None
    description: str | None = None
    legal_terms: str | None = None
    category: str | None = None
    is_default: bool | None = None


class ProposalTemplateResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    body: str
    legal_terms: str | None = None
    category: str | None = None
    is_default: bool
    owner_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreateFromTemplateRequest(BaseModel):
    template_id: int
    contact_id: int
    company_id: int | None = None
    custom_variables: dict | None = None

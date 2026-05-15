"""Pydantic schemas for proposals."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, model_validator

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

    page: int = Field(ge=1)
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    w: float = Field(gt=0)
    h: float = Field(gt=0)


class ProposalBillingMixin(BaseModel):
    """Structured pricing fields shared by ProposalBase/Update/Response.

    When payment_type='subscription', recurring_interval and
    recurring_interval_count must both be set. Validated at the Pydantic
    layer so the Stripe path never sees a half-configured subscription.
    """
    payment_type: PaymentType = "one_time"
    recurring_interval: RecurringInterval | None = None
    recurring_interval_count: int | None = None
    amount: Decimal | None = None
    currency: str = "USD"

    @model_validator(mode="after")
    def _check_recurring(self) -> "ProposalBillingMixin":
        if self.payment_type == "subscription":
            if not self.recurring_interval or not self.recurring_interval_count:
                raise ValueError(
                    "subscription proposals require recurring_interval and "
                    "recurring_interval_count",
                )
            if self.recurring_interval_count < 1:
                raise ValueError("recurring_interval_count must be >= 1")
        # one_time must not carry recurrence hints; reject so we don't
        # store contradictory state at the DB layer.
        elif self.recurring_interval is not None or self.recurring_interval_count is not None:
            raise ValueError(
                "one_time proposals must not set recurring_interval/count",
            )
        if self.amount is not None and self.amount <= 0:
            raise ValueError("amount must be > 0")
        return self


# Proposal Schemas

class ProposalBase(ProposalBillingMixin):
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
    payment_type: PaymentType | None = None
    recurring_interval: RecurringInterval | None = None
    recurring_interval_count: int | None = None
    amount: Decimal | None = None
    currency: str | None = None
    # Visual signature placement. ``None`` (explicitly) clears the row
    # back to auto-box. Validated against ``SignatureFieldCoords``;
    # ``exclude_unset=True`` in the service layer means an absent field
    # leaves the existing value alone.
    signature_field_coords: SignatureFieldCoords | None = None

    @model_validator(mode="after")
    def _check_billing_consistency(self) -> "ProposalUpdate":
        """Validate the subset of billing fields present in a PATCH.

        Partial updates pass this validator, but if any billing field is
        *explicitly* set, the combination still has to be internally
        consistent so we never land a half-configured subscription in
        the DB.
        """
        if self.payment_type == "subscription":
            # When turning a proposal into a subscription, interval + count
            # must land in the same PATCH (the service layer doesn't
            # merge-then-validate against the existing row).
            if not self.recurring_interval or not self.recurring_interval_count:
                raise ValueError(
                    "switching to subscription requires recurring_interval "
                    "and recurring_interval_count in the same update",
                )
            if self.recurring_interval_count < 1:
                raise ValueError("recurring_interval_count must be >= 1")
        elif self.payment_type == "one_time":
            if self.recurring_interval is not None or self.recurring_interval_count is not None:
                raise ValueError(
                    "one_time proposals must not set recurring_interval/count",
                )
        if self.amount is not None and self.amount <= 0:
            raise ValueError("amount must be > 0")
        return self


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


class ProposalRejectRequest(BaseModel):
    signer_email: EmailStr
    reason: str | None = None


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


class ProposalResponse(ProposalBase):
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
    # Visual signature placement on the master contract PDF, or NULL
    # when the stamper should auto-detect (bottom-right of last page).
    # Surfaced so the picker UI can re-open with the saved box drawn.
    signature_field_coords: SignatureFieldCoords | None = None
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
    # forensics / billing disputes.
    views: list[ProposalViewResponse] = []

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
    proposal_number: str
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
    payment_type: PaymentType = "one_time"
    recurring_interval: RecurringInterval | None = None
    recurring_interval_count: int | None = None
    amount: Decimal | None = None
    currency: str = "USD"
    # Payment URL is only populated after the client accepts and the
    # backend spawns a Stripe Invoice / Checkout Session. Surfaced here
    # so the public page can render a "Complete payment" CTA without a
    # second network round-trip.
    stripe_payment_url: str | None = None
    paid_at: datetime | None = None
    company: CompanyBrief | None = None
    contact: ContactBrief | None = None
    branding: ProposalBranding | None = None
    # Public-side attachment list. Surfaced for review; opening
    # everything is no longer a precondition to signing (Lorenzo's
    # 2026-05-14 ask — the T&C card inside the signing modal replaces
    # the forced-PDF-open gate).
    attachments: list[ProposalAttachmentPublicItem] = []
    # Resolved T&C body for the Sign-to-Confirm modal — proposal
    # override if set, else tenant default. NULL = no T&C card.
    terms_and_conditions: str | None = None
    # Designated signer's email, pre-filled (and locked) in the modal.
    designated_signer_email: str | None = None
    # When true, the accept endpoint stamps the drawn signature onto
    # the master PDF and returns a downloadable countersigned copy.
    has_master_contract: bool = False

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

"""Proposal service layer."""

import asyncio
import hashlib
import logging
import math
import re
import secrets
from datetime import UTC, datetime
from decimal import Decimal
from html import escape
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from botocore.exceptions import ClientError
from pypdf.errors import PdfReadError
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from src.activities.models import Activity
from src.attachments.models import Attachment
from src.attachments.object_storage import (
    delete_object,
    download_object_bytes,
    upload_file_bytes,
)
from src.attachments.service import AttachmentService
from src.config import settings
from src.core.base_service import BaseService, CRUDService, StatusTransitionMixin
from src.core.constants import DEFAULT_PAGE_SIZE
from src.core.filtering import build_token_search
from src.core.opportunity_guards import assert_opportunity_active
from src.core.sorting import build_order_clauses
from src.core.url_safety import UnsafeUrlError, validate_public_url
from src.email.branded_templates import (
    TenantBrandingHelper,
    render_contract_signed_email,
    render_proposal_email,
)
from src.email.pdf_render import pdf_logo_allowed_hosts, render_html_to_pdf
from src.email.service import EmailService, assert_gmail_connected
from src.email.types import EmailAttachment
from src.proposals.models import (
    Proposal,
    ProposalBundle,
    ProposalSigningDocument,
    ProposalTemplate,
    ProposalView,
)
from src.proposals.pdf_stamper import StampInputs, stamp_master_with_signature
from src.proposals.schemas import (
    ProposalBundleCreate,
    ProposalBundleUpdate,
    ProposalCreate,
    ProposalUpdate,
    SignatureFieldCoords,
    SignatureFieldPlacementValue,
    SignatureFieldPlacementWriteValue,
)

logger = logging.getLogger(__name__)

_TEMPLATE_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class _UnsetType:
    """Sentinel for distinguishing omitted PATCH fields from explicit nulls."""


_UNSET = _UnsetType()
def _single_coords_for_stamper(coords: dict) -> dict | None:
    try:
        page = int(coords["page"])
    except (KeyError, TypeError, ValueError):
        # Schema validation 422s the API surface, but an internal caller
        # bypassing it would otherwise hit a silent auto-box stamp.
        logger.warning(
            "Coercing malformed signature_field_coords to auto-box: %r",
            coords,
        )
        return None
    return {
        "page": max(0, page - 1),
        "x": coords.get("x"),
        "y": coords.get("y"),
        "width": coords.get("w"),
        "height": coords.get("h"),
    }


def _strict_coords_for_stamper(coords: object, *, index: int, field_name: str) -> dict:
    message = f"Malformed {field_name} placement at index {index}"
    if not isinstance(coords, dict):
        raise ValueError(message)

    try:
        page = int(coords["page"])
        x = float(coords["x"])
        y = float(coords["y"])
        width = float(coords["w"])
        height = float(coords["h"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(message) from exc

    if (
        page < 1
        or not all(math.isfinite(value) for value in (x, y, width, height))
        or width <= 0
        or height <= 0
    ):
        raise ValueError(message)

    return {
        "page": page - 1,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
    }


def _coords_for_stamper(
    coords: dict | list[dict] | None,
    *,
    field_name: str = "signature",
) -> dict | list[dict] | None:
    """Translate the user-facing ``SignatureFieldCoords`` shape into
    the dict ``pdf_stamper`` consumes.

    The picker UI persists ``{page (1-indexed), x, y, w, h}`` so the
    raw "Page N of M" label round-trips without an off-by-one trap.
    The stamper has always worked in ``{page (0-indexed), x, y, width,
    height}``; this is the single conversion point so neither layer
    has to know about the other's convention.

    A NULL/empty object payload returns ``None`` so the stamper falls
    through to ``_auto_box`` for legacy single-box callers. Array
    payloads are strict: saving multiple boxes means every entry must
    be valid, otherwise the signed PDF would silently omit or move a
    legally meaningful stamp.
    """
    if coords is None or coords == {}:
        return None
    if isinstance(coords, list):
        if not coords:
            raise ValueError(f"At least one {field_name} placement is required")
        return [
            _strict_coords_for_stamper(item, index=index, field_name=field_name)
            for index, item in enumerate(coords)
        ]
    return _single_coords_for_stamper(coords)


def _signed_date_label(signed_at: datetime, signer_timezone: str | None) -> str:
    """Format the signing date in the signer's local timezone."""
    local_dt = signed_at
    if signer_timezone:
        # ZoneInfo also raises ValueError for malformed strings (embedded
        # nulls, path-traversal attempts). Catch both so the outer accept
        # path doesn't blow up the whole stamp on garbage tz input.
        try:
            local_dt = signed_at.astimezone(ZoneInfo(signer_timezone))
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning("Unknown signer timezone %r; using UTC for signed date", signer_timezone)
    return local_dt.strftime("%m-%d-%Y")


PROPOSAL_SORTABLE_FIELDS: dict[str, Any] = {
    "proposal_number": Proposal.proposal_number,
    "title": Proposal.title,
    "status": Proposal.status,
    "view_count": Proposal.view_count,
    "created_at": Proposal.created_at,
}


def _designated_email_for(proposal: Proposal) -> str:
    """Lowercased email authorized to sign this proposal.

    Explicit ``designated_signer_email`` wins; otherwise fall back to the
    linked contact's email. Returns "" when neither is available.
    """
    if proposal.designated_signer_email:
        return proposal.designated_signer_email.strip().lower()
    if proposal.contact and proposal.contact.email:
        return proposal.contact.email.strip().lower()
    return ""


def _assert_signer_matches(proposal: Proposal, signer_email: str | None) -> str:
    """Guard: the supplied signer_email must match the proposal's designated
    recipient (case-insensitive). Shared by accept/reject so a forwarded
    public link can't be used by a third party to sign or reject.

    Returns the normalized (stripped+lowercased) email so callers can
    persist a consistent casing instead of the raw user-supplied value.
    A misconfigured proposal (no recipient on file) intentionally
    raises the same generic message as a mismatch — we don't want
    the public endpoint leaking server-side state.
    """
    expected = _designated_email_for(proposal)
    given = (signer_email or "").strip().lower()
    if not expected:
        logger.warning(
            "Proposal %s has no designated recipient — signer match cannot succeed",
            proposal.id,
        )
    if not expected or not given or given != expected:
        raise ValueError("Signer email does not match the proposal recipient")
    return given


def _clean_pdf_filename(filename: str | None) -> str:
    name = (filename or "signing-document.pdf").replace("\\", "/").rsplit("/", 1)[-1]
    name = name.strip() or "signing-document.pdf"
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return name[:255]


def _coords_to_dict(
    coords: SignatureFieldPlacementValue | dict | list[dict] | None,
) -> dict | list[dict] | None:
    if coords is None:
        return None
    if isinstance(coords, SignatureFieldCoords):
        return coords.model_dump()
    if isinstance(coords, list):
        return [
            item.model_dump() if isinstance(item, SignatureFieldCoords) else item for item in coords
        ]
    return coords


class ProposalService(StatusTransitionMixin, CRUDService[Proposal, ProposalCreate, ProposalUpdate]):
    """Service for Proposal CRUD operations."""

    model = Proposal
    create_exclude_fields = set()
    update_exclude_fields = set()

    def _get_eager_load_options(self):
        # ``Proposal.quote`` eager-load dropped 2026-05-14 — relationship
        # removed with the quotes router unmount; column persists.
        return [
            selectinload(Proposal.opportunity),
            selectinload(Proposal.contact),
            selectinload(Proposal.company),
            selectinload(Proposal.views),
            selectinload(Proposal.created_by_user),
            selectinload(Proposal.owner),
            selectinload(Proposal.signing_documents),
            selectinload(Proposal.bundle).selectinload(ProposalBundle.proposals),
        ]

    async def _generate_proposal_number(self) -> str:
        """Generate auto-incrementing proposal number: PR-{year}-{seq}.

        Uses the largest existing suffix + 1, not COUNT(*), so a deleted
        proposal in the middle of the sequence doesn't cause the next
        creator to collide on a still-present number. Concurrent creates
        can still race; the create() caller retries on IntegrityError.
        """
        year = datetime.now(UTC).year
        prefix = f"PR-{year}-"

        result = await self.db.execute(
            select(Proposal.proposal_number)
            .where(Proposal.proposal_number.like(f"{prefix}%"))
            .order_by(Proposal.proposal_number.desc())
            .limit(1)
        )
        last = result.scalar_one_or_none()
        if last is None:
            seq = 1
        else:
            try:
                seq = int(last.removeprefix(prefix)) + 1
            except ValueError:
                # Suffix isn't numeric (legacy / hand-edited row). Fall
                # back to count to keep moving instead of 500-ing.
                count_result = await self.db.execute(
                    select(func.count(Proposal.id)).where(
                        Proposal.proposal_number.like(f"{prefix}%")
                    )
                )
                seq = (count_result.scalar() or 0) + 1
        return f"{prefix}{seq:04d}"

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        search: str | None = None,
        status: str | None = None,
        contact_id: int | None = None,
        company_id: int | None = None,
        opportunity_id: int | None = None,
        quote_id: int | None = None,
        owner_id: int | None = None,
        shared_entity_ids: list[int] | None = None,
        order_by: str | None = None,
        order_dir: str | None = None,
        include_bundle_options: bool = False,
    ) -> tuple[list[Proposal], int]:
        """Get paginated list of proposals with filters.

        By default, sub-options of a bundle (sort_order != 0) are hidden so
        the bundle surfaces as a single row on /proposals — the "parent
        representative". Pass ``include_bundle_options=True`` for admin /
        reporting use cases that need every row.
        """
        query = (
            select(Proposal)
            .options(
                selectinload(Proposal.opportunity),
                selectinload(Proposal.contact),
                selectinload(Proposal.company),
                selectinload(Proposal.created_by_user),
                selectinload(Proposal.owner),
                selectinload(Proposal.signing_documents),
                selectinload(Proposal.bundle).selectinload(ProposalBundle.proposals),
            )
        )

        if not include_bundle_options:
            # Sub-proposals live ONLY under their parent (sort_order=0) on the
            # detail page — they shouldn't pollute the list. A NULL bundle id
            # means "standalone proposal" and stays visible regardless.
            query = query.where(
                or_(
                    Proposal.proposal_bundle_id.is_(None),
                    Proposal.bundle_sort_order == 0,
                )
            )

        if search:
            search_condition = build_token_search(search, Proposal.title, Proposal.proposal_number)
            if search_condition is not None:
                query = query.where(search_condition)

        if status:
            query = query.where(Proposal.status == status)

        if contact_id:
            query = query.where(Proposal.contact_id == contact_id)

        if company_id:
            query = query.where(Proposal.company_id == company_id)

        if opportunity_id:
            query = query.where(Proposal.opportunity_id == opportunity_id)

        if quote_id:
            query = query.where(Proposal.quote_id == quote_id)

        if owner_id:
            if shared_entity_ids:
                query = query.where(
                    or_(Proposal.owner_id == owner_id, Proposal.id.in_(shared_entity_ids))
                )
            else:
                query = query.where(Proposal.owner_id == owner_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        order_clauses = build_order_clauses(
            PROPOSAL_SORTABLE_FIELDS,
            order_by,
            order_dir,
            default=[Proposal.created_at.desc(), Proposal.id.desc()],
        )
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(*order_clauses)

        result = await self.db.execute(query)
        proposals = list(result.scalars().all())

        return proposals, total

    async def _generate_bundle_number(self) -> str:
        year = datetime.now(UTC).year
        prefix = f"PB-{year}-"
        # Match _generate_proposal_number's shape: count-based, predictable, no
        # silent-fallback branch. A malformed bundle_number on the latest row
        # should fail loud (the prior fallback would have silently re-issued a
        # non-monotonic sequence on top of corrupted data).
        count_result = await self.db.execute(
            select(func.count(ProposalBundle.id)).where(
                ProposalBundle.bundle_number.like(f"{prefix}%")
            )
        )
        seq = (count_result.scalar() or 0) + 1
        return f"{prefix}{seq:04d}"

    async def get_bundle(self, bundle_id: int) -> ProposalBundle | None:
        result = await self.db.execute(
            select(ProposalBundle)
            .options(
                selectinload(ProposalBundle.proposals).selectinload(Proposal.signing_documents),
                selectinload(ProposalBundle.proposals).selectinload(Proposal.contact),
                selectinload(ProposalBundle.proposals).selectinload(Proposal.company),
                selectinload(ProposalBundle.contact),
                selectinload(ProposalBundle.company),
                selectinload(ProposalBundle.created_by_user),
                selectinload(ProposalBundle.owner),
            )
            .where(ProposalBundle.id == bundle_id)
        )
        return result.scalar_one_or_none()

    async def get_public_bundle(self, token: str) -> ProposalBundle | None:
        if not token or len(token) < 16:
            return None
        result = await self.db.execute(
            select(ProposalBundle)
            .options(
                selectinload(ProposalBundle.proposals).selectinload(Proposal.contact),
                selectinload(ProposalBundle.proposals).selectinload(Proposal.company),
                selectinload(ProposalBundle.proposals).selectinload(Proposal.signing_documents),
                selectinload(ProposalBundle.contact),
                selectinload(ProposalBundle.company),
            )
            .where(ProposalBundle.public_token == token)
        )
        return result.scalar_one_or_none()

    async def record_bundle_view(self, bundle: ProposalBundle) -> None:
        # Don't re-arm sibling status on an already-closed bundle. Once a
        # sibling was accepted, the other siblings are correctly `rejected`;
        # if a previous flush left any in `sent` (e.g. a partial failure),
        # they must NOT bounce back to `viewed` here — that would expose
        # them as actionable to a customer who refreshed the chooser page
        # after acceptance, widening the accept-race window.
        if bundle.status in ("accepted", "rejected"):
            return
        now = datetime.now(UTC)
        bundle.viewed_at = now
        if bundle.status == "sent":
            bundle.status = "viewed"
        for proposal in bundle.proposals or []:
            if proposal.status == "sent":
                proposal.status = "viewed"
                proposal.viewed_at = proposal.viewed_at or now
        await self.db.flush()

    async def create_bundle(self, data: ProposalBundleCreate, user_id: int) -> ProposalBundle:
        proposal_ids = list(dict.fromkeys(data.proposal_ids))
        if len(proposal_ids) < 2:
            raise ValueError("Choose at least two proposals for a bundle")
        proposals = await self._load_bundle_proposals(proposal_ids)
        self._validate_bundle_proposals_mutable(proposals)
        first = proposals[0]
        title = data.title.strip()
        if not title:
            raise ValueError("Bundle title is required")
        bundle = ProposalBundle(
            bundle_number=await self._generate_bundle_number(),
            public_token=secrets.token_urlsafe(32),
            title=title,
            description=data.description,
            status="draft",
            contact_id=first.contact_id,
            company_id=first.company_id,
            owner_id=first.owner_id or user_id,
            created_by_id=user_id,
        )
        self.db.add(bundle)
        await self.db.flush()
        for index, proposal in enumerate(proposals):
            proposal.proposal_bundle_id = bundle.id
            proposal.bundle_sort_order = index
            proposal.bundle_is_recommended = index == 0
        await self.db.flush()
        await self.db.refresh(bundle)
        return bundle

    async def update_bundle(
        self,
        bundle: ProposalBundle,
        data: ProposalBundleUpdate,
        user_id: int,
    ) -> ProposalBundle | None:
        """Update a bundle. Returns None when the update dissolved the bundle
        (proposal_ids shrank to 1) so the router can emit 204."""
        if bundle.status not in ("draft",):
            raise ValueError("Proposal bundles can only be changed while draft")

        fields_set = data.model_fields_set
        values = data.model_dump(
            exclude_unset=True,
            exclude={"proposal_ids", "recommended_proposal_id"},
        )
        if "title" in values and values["title"] is not None:
            values["title"] = values["title"].strip()
            if not values["title"]:
                raise ValueError("Bundle title is required")
        for key, value in values.items():
            setattr(bundle, key, value)

        if data.proposal_ids is not None:
            proposal_ids = list(dict.fromkeys(data.proposal_ids))
            if len(proposal_ids) == 0:
                raise ValueError("Bundle must reference at least one proposal")

            if len(proposal_ids) == 1:
                # Dissolve: unbundle the survivor and any removed siblings,
                # then drop the bundle row itself.
                survivors = await self._load_bundle_proposals(proposal_ids)
                survivor = survivors[0]
                if survivor.proposal_bundle_id not in (None, bundle.id):
                    raise ValueError("A proposal can only belong to one bundle")
                for existing in list(bundle.proposals):
                    existing.proposal_bundle_id = None
                    existing.bundle_sort_order = 0
                    existing.bundle_is_recommended = False
                await self.db.delete(bundle)
                await self.db.flush()
                return None

            proposals = await self._load_bundle_proposals(proposal_ids)
            self._validate_bundle_proposals_mutable(proposals, bundle_id=bundle.id)

            # Remember which proposal was recommended BEFORE we churn the
            # membership — we want to preserve a user-chosen recommendation
            # across "add/remove option" actions instead of silently snapping
            # it back to the new index==0 the way the original code did.
            prior_recommended_id: int | None = next(
                (p.id for p in bundle.proposals if p.bundle_is_recommended),
                None,
            )
            for existing in list(bundle.proposals):
                if existing.id not in proposal_ids:
                    existing.proposal_bundle_id = None
                    existing.bundle_sort_order = 0
                    existing.bundle_is_recommended = False
            for index, proposal in enumerate(proposals):
                proposal.proposal_bundle_id = bundle.id
                proposal.bundle_sort_order = index
            # If the previously-recommended option survived, keep flagging it;
            # otherwise clear all (no auto-fallback to index==0 on an update
            # — only the create path defaults to "first is recommended").
            if prior_recommended_id is not None and any(
                p.id == prior_recommended_id for p in proposals
            ):
                for proposal in proposals:
                    proposal.bundle_is_recommended = proposal.id == prior_recommended_id
            else:
                for proposal in proposals:
                    proposal.bundle_is_recommended = False

        # An explicit `recommended_proposal_id` in the payload overrides the
        # preservation logic above. `null` means "no option is recommended"
        # (no badge). An integer must point at a current member.
        if "recommended_proposal_id" in fields_set:
            target_id = data.recommended_proposal_id
            await self.db.refresh(bundle, attribute_names=["proposals"])
            members_by_id = {p.id: p for p in bundle.proposals}
            if target_id is not None and target_id not in members_by_id:
                raise ValueError("Recommended proposal is not a member of this bundle")
            for proposal in bundle.proposals:
                proposal.bundle_is_recommended = (
                    target_id is not None and proposal.id == target_id
                )

        bundle.updated_by_id = user_id
        await self.db.flush()
        await self.db.refresh(bundle)
        return bundle

    async def remove_option_from_bundle(
        self,
        bundle: ProposalBundle,
        proposal_id: int,
        user_id: int,
    ) -> ProposalBundle | None:
        """Remove one proposal from the bundle. Dissolves when ≤1 survivor.

        Goes around `update_bundle` so we can take the dissolve path
        (1 survivor) without tripping the schema-level
        ProposalBundleUpdate.proposal_ids min_length=2 guard that protects
        the public PATCH route.
        """
        if bundle.status not in ("draft",):
            raise ValueError("Proposal bundles can only be changed while draft")
        members = list(bundle.proposals)
        member = next((p for p in members if p.id == proposal_id), None)
        if member is None:
            raise ValueError("Proposal is not part of this bundle")

        survivors = [p for p in members if p.id != proposal_id]

        # Unbundle the proposal being removed.
        member.proposal_bundle_id = None
        member.bundle_sort_order = 0
        member.bundle_is_recommended = False

        if len(survivors) <= 1:
            # Dissolve: unbundle every survivor (there's at most one) and
            # drop the bundle row.
            for survivor in survivors:
                survivor.proposal_bundle_id = None
                survivor.bundle_sort_order = 0
                survivor.bundle_is_recommended = False
            await self.db.delete(bundle)
            await self.db.flush()
            return None

        # 2+ survivors: re-pack sort_order, keep any prior recommendation that
        # didn't belong to the removed option.
        for index, survivor in enumerate(survivors):
            survivor.bundle_sort_order = index
        bundle.updated_by_id = user_id
        await self.db.flush()
        await self.db.refresh(bundle)
        return bundle

    async def _load_bundle_proposals(self, proposal_ids: list[int]) -> list[Proposal]:
        result = await self.db.execute(
            select(Proposal)
            .options(selectinload(Proposal.signing_documents), selectinload(Proposal.bundle))
            .where(Proposal.id.in_(proposal_ids))
        )
        proposals_by_id = {proposal.id: proposal for proposal in result.scalars().all()}
        missing = [proposal_id for proposal_id in proposal_ids if proposal_id not in proposals_by_id]
        if missing:
            raise ValueError(f"Proposal not found: {missing[0]}")
        return [proposals_by_id[proposal_id] for proposal_id in proposal_ids]

    def _validate_bundle_proposals_mutable(
        self,
        proposals: list[Proposal],
        *,
        bundle_id: int | None = None,
    ) -> None:
        statuses = {proposal.status for proposal in proposals}
        if statuses - {"draft"}:
            raise ValueError("Only draft proposals can be added to a bundle")
        contacts = {proposal.contact_id for proposal in proposals}
        if len(contacts) > 1:
            raise ValueError("Bundled proposals must target the same contact")
        companies = {proposal.company_id for proposal in proposals}
        if len(companies) > 1:
            raise ValueError("Bundled proposals must target the same company")
        for proposal in proposals:
            if proposal.proposal_bundle_id not in (None, bundle_id):
                raise ValueError("A proposal can only belong to one bundle")

    async def validate_bundle_ready(self, bundle: ProposalBundle) -> None:
        proposals = list(bundle.proposals or [])
        if len(proposals) < 2:
            raise ValueError("A proposal bundle needs at least two proposals")
        for proposal in proposals:
            await self.validate_signing_documents_ready(proposal)
            if not proposal.contact_id and not bundle.contact_id:
                raise ValueError("Every bundled proposal needs an associated contact")

    async def send_bundle_email(
        self,
        bundle_id: int,
        user_id: int,
    ) -> ProposalBundle:
        await assert_gmail_connected(self.db, user_id)
        bundle = await self.get_bundle(bundle_id)
        if not bundle:
            raise ValueError(f"Proposal bundle {bundle_id} not found")
        await self.validate_bundle_ready(bundle)
        proposal = (bundle.proposals or [None])[0]
        contact = proposal.contact if proposal and proposal.contact else bundle.contact
        if not contact or not getattr(contact, "email", None):
            raise ValueError("Bundle contact has no email address")
        if not bundle.public_token:
            bundle.public_token = secrets.token_urlsafe(32)
        branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)
        base_url = settings.FRONTEND_BASE_URL or "http://localhost:3000"
        view_url = f"{base_url}/proposals/public/{bundle.public_token}"
        subject, html_body = render_proposal_email(
            branding,
            {
                "proposal_title": bundle.title,
                "client_name": getattr(contact, "first_name", None) or str(contact),
                "summary": bundle.description or "",
                "view_url": view_url,
            },
        )
        await EmailService(self.db).queue_email(
            to_email=contact.email,
            subject=subject,
            body=html_body,
            sent_by_id=user_id,
            entity_type="proposal_bundles",
            entity_id=bundle.id,
        )
        now = datetime.now(UTC)
        bundle.status = "sent"
        bundle.sent_at = bundle.sent_at or now
        for option in bundle.proposals:
            if option.status == "draft":
                option.status = "sent"
                option.sent_at = option.sent_at or now
        await self.db.flush()
        await self.db.refresh(bundle)
        return bundle

    async def update(
        self,
        instance: Proposal,
        data: ProposalUpdate,
        user_id: int,
    ) -> Proposal:
        """Reject edits once the customer has signed; clone or void instead."""
        if instance.signed_at is not None:
            raise ValueError(
                "Proposal has been signed and is locked — clone it to make changes",
            )
        # Mirror the create-path Closed-Lost guard: a PATCH that retargets
        # the proposal at a Closed-Lost opportunity would otherwise
        # silently bypass the create check.
        update_fields = data.model_dump(exclude_unset=True)
        new_opp = update_fields.get("opportunity_id")
        if new_opp is not None and new_opp != instance.opportunity_id:
            await assert_opportunity_active(self.db, new_opp, "proposal")
        return await super().update(instance, data, user_id)

    async def list_signing_documents(
        self,
        proposal_id: int,
    ) -> list[ProposalSigningDocument]:
        result = await self.db.execute(
            select(ProposalSigningDocument)
            .where(ProposalSigningDocument.proposal_id == proposal_id)
            .order_by(
                ProposalSigningDocument.display_order.asc(),
                ProposalSigningDocument.id.asc(),
            )
        )
        return list(result.scalars().all())

    async def get_signing_document(
        self,
        proposal_id: int,
        document_id: int,
    ) -> ProposalSigningDocument | None:
        result = await self.db.execute(
            select(ProposalSigningDocument)
            .where(ProposalSigningDocument.proposal_id == proposal_id)
            .where(ProposalSigningDocument.id == document_id)
        )
        return result.scalar_one_or_none()

    async def upload_signing_document_pdf(
        self,
        proposal: Proposal,
        content: bytes,
        filename: str | None,
        user_id: int,
    ) -> ProposalSigningDocument:
        """Persist one signable PDF that needs an explicit signature box."""
        if proposal.signed_at is not None:
            raise ValueError(
                "Cannot modify signing documents on a signed proposal — clone it instead",
            )
        if not content:
            raise ValueError("signing document PDF is empty")
        if not content.startswith(b"%PDF-"):
            raise ValueError("signing document must be a PDF file")
        if len(content) > 25 * 1024 * 1024:
            raise ValueError("signing document exceeds 25 MB limit")

        count_result = await self.db.execute(
            select(func.count(ProposalSigningDocument.id)).where(
                ProposalSigningDocument.proposal_id == proposal.id,
            )
        )
        display_order = int(count_result.scalar() or 0)
        document = ProposalSigningDocument(
            proposal_id=proposal.id,
            original_filename=_clean_pdf_filename(filename),
            file_size=len(content),
            content_type="application/pdf",
            pdf_path="",
            display_order=display_order,
            created_by_id=user_id,
        )
        self.db.add(document)
        await self.db.flush()

        key = f"proposals/{proposal.id}/signing-documents/{document.id}/source.pdf"
        await upload_file_bytes(content, key, content_type="application/pdf")
        document.pdf_path = key
        await self.db.flush()
        await self.db.refresh(document)
        return document

    async def update_signing_document(
        self,
        proposal: Proposal,
        document: ProposalSigningDocument,
        *,
        signature_field_coords: (
            SignatureFieldPlacementWriteValue | dict | list[dict] | None | _UnsetType
        ) = _UNSET,
        date_field_coords: (
            SignatureFieldPlacementWriteValue | dict | list[dict] | None | _UnsetType
        ) = _UNSET,
        user_id: int,
    ) -> ProposalSigningDocument:
        if proposal.signed_at is not None:
            raise ValueError(
                "Cannot modify signing documents on a signed proposal — clone it instead",
            )
        if not isinstance(signature_field_coords, _UnsetType):
            document.signature_field_coords = _coords_to_dict(signature_field_coords)
        if not isinstance(date_field_coords, _UnsetType):
            document.date_field_coords = _coords_to_dict(date_field_coords)
        document.updated_by_id = user_id
        await self.db.flush()
        await self.db.refresh(document)
        return document

    async def delete_signing_document(
        self,
        proposal: Proposal,
        document: ProposalSigningDocument,
    ) -> None:
        if proposal.signed_at is not None:
            raise ValueError(
                "Cannot modify signing documents on a signed proposal — clone it instead",
            )
        object_keys = [
            key for key in (document.pdf_path, document.signed_pdf_path) if key
        ]
        await self.db.delete(document)
        await self.db.flush()
        for key in object_keys:
            await delete_object(key)

    async def validate_signing_documents_ready(
        self,
        proposal: Proposal,
        *,
        require_date: bool = True,
    ) -> None:
        """Block send/sign when an uploaded signing PDF has incomplete placement."""
        documents = await self.list_signing_documents(proposal.id)
        incomplete = [
            doc.original_filename
            for doc in documents
            if (
                not doc.pdf_path
                or not doc.signature_field_coords
                or (require_date and not doc.date_field_coords)
            )
        ]
        if incomplete:
            names = ", ".join(incomplete[:3])
            if len(incomplete) > 3:
                names = f"{names}, +{len(incomplete) - 3} more"
            raise ValueError(
                "Place signature and date areas on every signing document before sending "
                f"({names})",
            )

        # Compatibility path for pre-multi-doc rows or old clients still
        # using /master-contract. New documents are validated above.
        if (
            not documents
            and proposal.master_contract_pdf_path
            and (
                not proposal.signature_field_coords
                or (require_date and not proposal.date_field_coords)
            )
        ):
            raise ValueError(
                "Place signature and date areas on the master service agreement before sending",
            )

    async def create(self, data: ProposalCreate, user_id: int) -> Proposal:
        """Create a new proposal with auto-generated number + public token.

        proposal_number is generated outside any DB lock, so two concurrent
        creates can land on the same suffix and one of them hits the
        ``ix_proposals_proposal_number`` unique violation. We retry a small
        number of times — each iteration recomputes max-suffix+1 against
        the now-committed competing row.
        """
        if data.opportunity_id is not None:
            await assert_opportunity_active(self.db, data.opportunity_id, "proposal")

        proposal_data = data.model_dump()
        proposal_data["public_token"] = secrets.token_urlsafe(32)
        proposal_data["created_by_id"] = user_id
        # Default ownership to the creating user when the form didn't
        # specify one. owner_id is load-bearing downstream: it drives
        # tenant-branding lookups (public proposal page colors/logo),
        # signed-PDF email routing through the owner's Gmail OAuth,
        # and "my proposals" data scoping. A NULL owner silently falls
        # back to the generic "CRM" defaults and Resend, which is why
        # early Link Creative proposals rendered unbranded.
        if proposal_data.get("owner_id") is None:
            proposal_data["owner_id"] = user_id

        last_error: IntegrityError | None = None
        for _ in range(5):
            proposal_data["proposal_number"] = await self._generate_proposal_number()
            proposal = Proposal(**proposal_data)
            try:
                # Savepoint isolates the INSERT so a unique-violation on
                # proposal_number rolls back just this attempt, not the
                # outer request transaction (which will also commit the
                # audit row written by the router).
                async with self.db.begin_nested():
                    self.db.add(proposal)
                    await self.db.flush()
            except IntegrityError as exc:
                if "ix_proposals_proposal_number" not in str(exc.orig):
                    raise
                last_error = exc
                continue
            await self.db.refresh(proposal)
            return proposal

        raise last_error or RuntimeError(
            "Could not generate a unique proposal_number after 5 attempts",
        )

    async def accept_proposal_public(
        self,
        proposal: Proposal,
        signer_name: str,
        signer_email: str,
        signature_image: bytes,
        agreed_to_terms: bool,
        signer_ip: str | None = None,
        signer_user_agent: str | None = None,
        signer_timezone: str | None = None,
        selected_proposal_id: int | None = None,
    ) -> tuple[Proposal, list[Proposal]]:
        """Accept a proposal via the public Sign-to-Confirm modal.

        Persists the drawn signature, transitions the proposal to
        ``accepted``, then — when a master service agreement PDF is on
        file — stamps the signature onto a copy + appends an audit
        page and uploads the composite to R2. Emails the signer a
        countersigned copy.

        No proposal-side Stripe spawn; any new payment collection starts in
        the Payments module after acceptance. Signer
        email must match the proposal's designated recipient and
        ``agreed_to_terms`` must be True (ESIGN Act consent).

        Raises ValueError if status isn't sent/viewed, the signer
        email doesn't match, consent isn't given, or the proposal is
        past its ``valid_until`` date.
        """
        now = datetime.now(UTC)
        if proposal.status not in ("sent", "viewed"):
            raise ValueError(f"Cannot accept proposal in '{proposal.status}' status")

        # Hard-block expired proposals server-side. The public page
        # already shows "Expired" in the UI, but without this a signer
        # could craft a direct POST and sign past the expiry, which
        # undermines the "Valid until" commitment they saw.
        if proposal.valid_until and proposal.valid_until < now.date():
            raise ValueError(
                f"This proposal expired on {proposal.valid_until.isoformat()} "
                "and can no longer be accepted",
            )
        # In-flight proposals (sent before this PR) have signature placement
        # but no date placement. Don't block accept on missing date coords —
        # the date stamp is fail-soft (UTC fallback in stamper). The send
        # gate is the right place to enforce both.
        await self.validate_signing_documents_ready(proposal, require_date=False)

        # Validate the submitted payload (consent + signature) BEFORE the
        # signer-email authz check so a customer who forgot to tick the
        # box doesn't see a confusing "email mismatch" error. The
        # consent/signature checks are payload-shape only; they leak no
        # information about the proposal recipient.
        if not agreed_to_terms:
            raise ValueError(
                "You must agree to the terms and conditions to sign this proposal",
            )

        if not signature_image:
            raise ValueError("Signature image is required")

        normalized_signer_email = _assert_signer_matches(proposal, signer_email)
        if selected_proposal_id is not None and selected_proposal_id != proposal.id:
            raise ValueError("Selected proposal does not match the proposal being signed")

        # Bundle invariant: only one sibling can ever reach `accepted`. Two
        # signers hitting two different sibling URLs concurrently each pass
        # their own per-proposal conditional UPDATE (different rows), so the
        # serialization point has to live on the bundle row. Acquire FOR
        # UPDATE on the bundle BEFORE the per-proposal UPDATE — the second
        # accept blocks until the first commits, then sees status='accepted'
        # and refuses. A partial unique index on
        # proposals(proposal_bundle_id) WHERE status IN ('accepted','awaiting_payment','paid')
        # (migration 047) is the DB-level backstop if the app-layer guard is
        # ever bypassed.
        locked_bundle: ProposalBundle | None = None
        if proposal.proposal_bundle_id is not None:
            bundle_lock = await self.db.execute(
                select(ProposalBundle)
                .options(selectinload(ProposalBundle.proposals))
                .where(ProposalBundle.id == proposal.proposal_bundle_id)
                .with_for_update()
            )
            locked_bundle = bundle_lock.scalar_one_or_none()
            if locked_bundle is None:
                raise ValueError(
                    f"Proposal {proposal.id} references missing bundle "
                    f"{proposal.proposal_bundle_id}",
                )
            if locked_bundle.selected_proposal_id is not None and locked_bundle.selected_proposal_id != proposal.id:
                raise ValueError(
                    "Another proposal in this bundle was already accepted",
                )
            if locked_bundle.status == "accepted":
                raise ValueError(
                    "Another proposal in this bundle was already accepted",
                )

        # Atomic status transition: conditional UPDATE guarded by the
        # same (sent|viewed) whitelist. If two accept requests arrive
        # concurrently, only one row update will match — the other
        # returns rowcount=0 and we raise instead of double-stamping
        # the master PDF.
        stmt = (
            update(Proposal)
            .where(Proposal.id == proposal.id)
            .where(Proposal.status.in_(("sent", "viewed")))
            .values(
                status="accepted",
                accepted_at=now,
                signer_name=signer_name,
                signer_email=normalized_signer_email,
                signer_ip=signer_ip,
                signer_user_agent=signer_user_agent,
                signer_timezone=signer_timezone,
                signed_at=now,
                signature_image=signature_image,
            )
        )
        result = await self.db.execute(stmt)
        if result.rowcount == 0:
            raise ValueError(
                "Proposal was accepted by another signer moments ago",
            )
        await self.db.flush()
        await self.db.refresh(proposal)
        rejected_siblings: list[Proposal] = []
        if locked_bundle is not None:
            rejected_siblings = await self._mark_bundle_accepted(
                proposal, locked_bundle, accepted_at=now,
            )

        # Stamp + upload the master PDF if Lorenzo attached one. Failure
        # is logged but does not unwind the acceptance — the signed-row
        # + signature_image bytes alone are ESIGN-Act § 7001-compliant
        # evidence and the operator can re-stamp later.
        await self._maybe_stamp_signing_documents(
            proposal,
            signer_ip=signer_ip,
            signer_user_agent=signer_user_agent,
            signed_at=now,
            signer_timezone=signer_timezone,
        )

        # Mail the signer a signed PDF copy for their records.
        await self.send_signed_copy_to_client(proposal)

        # Owner-side proposal_signed notification — matrix-gated; signer
        # already received their always-on signed copy above. Import is
        # outside the try so an ImportError surfaces loudly rather than
        # masquerading as a runtime swallow.
        if proposal.owner_id:
            from src.notifications.service import notify_on_proposal_signed  # noqa: PLC0415

            try:
                await notify_on_proposal_signed(
                    db=self.db,
                    owner_id=proposal.owner_id,
                    proposal_id=proposal.id,
                    proposal_title=proposal.title,
                    signer_name=proposal.signer_name,
                    signed_at=(
                        proposal.signed_at.strftime("%B %d, %Y · %H:%M UTC")
                        if proposal.signed_at
                        else None
                    ),
                )
            except Exception:
                logger.exception(
                    "proposal_signed notify failed for proposal %s", proposal.id,
                )

        await self.db.refresh(proposal)
        return proposal, rejected_siblings

    async def _mark_bundle_accepted(
        self,
        selected: Proposal,
        bundle: ProposalBundle,
        *,
        accepted_at: datetime,
    ) -> list[Proposal]:
        # Caller (accept_proposal_public) acquired FOR UPDATE on this bundle
        # row and pre-loaded bundle.proposals; this method just mutates under
        # that lock and never re-queries.
        bundle.status = "accepted"
        bundle.selected_proposal_id = selected.id
        bundle.selected_at = accepted_at
        bundle.accepted_at = accepted_at
        actor_id = selected.owner_id or selected.created_by_id
        rejected_siblings: list[Proposal] = []
        for option in bundle.proposals:
            if option.id != selected.id and option.status in ("sent", "viewed"):
                option.status = "rejected"
                option.rejected_at = accepted_at
                option.rejection_reason = (
                    f"Another proposal in bundle {bundle.bundle_number} was accepted."
                )
                rejected_siblings.append(option)
                # Per-sibling Activity row so the owner's timeline shows the
                # full picture, not just the winner. emit() runs in the
                # router after _mark_bundle_accepted returns — keeping IO
                # out of the locked critical section.
                if actor_id:
                    self.db.add(
                        Activity(
                            activity_type="note",
                            subject=f"Proposal rejected: {option.title}",
                            description=(
                                f"Auto-rejected because another proposal in "
                                f"bundle {bundle.bundle_number} was accepted."
                            ),
                            entity_type="proposals",
                            entity_id=option.id,
                            is_completed=True,
                            completed_at=accepted_at,
                            owner_id=actor_id,
                            created_by_id=actor_id,
                        )
                    )
        if actor_id:
            self.db.add(
                Activity(
                    activity_type="note",
                    subject=f"Proposal bundle selected: {selected.title}",
                    description=f"Selected from bundle {bundle.bundle_number}.",
                    entity_type="proposals",
                    entity_id=selected.id,
                    is_completed=True,
                    completed_at=accepted_at,
                    owner_id=actor_id,
                    created_by_id=actor_id,
                )
            )
        # Return the rejected siblings so the router can emit PROPOSAL_REJECTED
        # events post-commit. Avoids importing the events module from the
        # service layer, and emitting under the row lock would tie event-
        # handler latency to the bundle's serialization window.
        await self.db.flush()
        return rejected_siblings

    async def _maybe_stamp_signing_documents(
        self,
        proposal: Proposal,
        signer_ip: str | None,
        signer_user_agent: str | None,
        signed_at: datetime,
        signer_timezone: str | None,
    ) -> None:
        documents = await self.list_signing_documents(proposal.id)
        if not documents:
            await self._maybe_stamp_master_pdf(
                proposal,
                signer_ip=signer_ip,
                signer_user_agent=signer_user_agent,
                signed_at=signed_at,
                signer_timezone=signer_timezone,
            )
            return
        if proposal.signature_image is None:
            return

        first_signed_key: str | None = None
        failed_count = 0
        for document in documents:
            try:
                master_bytes = await download_object_bytes(document.pdf_path)
                stamped = await asyncio.to_thread(
                    stamp_master_with_signature,
                    StampInputs(
                        master_pdf=master_bytes,
                        signature_png=proposal.signature_image,
                        coords=_coords_for_stamper(
                            document.signature_field_coords,
                            field_name="signature",
                        ),
                        date_coords=_coords_for_stamper(
                            document.date_field_coords,
                            field_name="date",
                        ),
                        date_label=_signed_date_label(signed_at, signer_timezone),
                        signer_name=proposal.signer_name or "",
                        signer_email=proposal.signer_email or "",
                        signer_ip=signer_ip,
                        signer_user_agent=signer_user_agent,
                        signed_at=signed_at,
                        proposal_number=proposal.proposal_number,
                    ),
                )
                timestamp = int(signed_at.timestamp())
                signed_key = (
                    f"proposals/{proposal.id}/signing-documents/"
                    f"{document.id}/signed-{timestamp}.pdf"
                )
                await upload_file_bytes(
                    stamped,
                    signed_key,
                    content_type="application/pdf",
                )
                document.signed_pdf_path = signed_key
                document.signed_pdf_error = None
                if first_signed_key is None:
                    first_signed_key = signed_key
            except PdfReadError as exc:
                logger.exception(
                    "Signing document unreadable for proposal %s document %s",
                    proposal.id,
                    document.id,
                )
                failed_count += 1
                document.signed_pdf_error = (
                    f"Signing document is corrupt or unreadable: {str(exc)[:900]}"
                )
            except ClientError as exc:
                logger.exception(
                    "R2 storage error stamping proposal %s document %s",
                    proposal.id,
                    document.id,
                )
                failed_count += 1
                response = getattr(exc, "response", None)
                err = response.get("Error", {}) if isinstance(response, dict) else {}
                code = err.get("Code", "ClientError")
                message = err.get("Message", str(exc))
                document.signed_pdf_error = (
                    f"Object storage temporarily unavailable ({code}): {message}"[:1000]
                )
            except Exception as exc:
                logger.exception(
                    "Failed to stamp proposal %s signing document %s",
                    proposal.id,
                    document.id,
                )
                failed_count += 1
                document.signed_pdf_error = str(exc)[:1000]
            finally:
                await self._commit_stamp_capture(proposal.id)

        # Preserve the prior pointer when every per-doc stamp fails — a
        # transient R2 outage on Re-stamp must not destroy a previously-
        # working signed_pdf_path. Mirrors the fail-soft contract in
        # `_maybe_stamp_master_pdf` below.
        if first_signed_key is not None:
            proposal.signed_pdf_path = first_signed_key
        proposal.signed_pdf_error = (
            None
            if failed_count == 0
            else f"{failed_count} signing document(s) failed to generate a signed PDF"
        )
        await self._commit_stamp_capture(proposal.id)

    async def _maybe_stamp_master_pdf(
        self,
        proposal: Proposal,
        signer_ip: str | None,
        signer_user_agent: str | None,
        signed_at: datetime,
        signer_timezone: str | None,
    ) -> None:
        """Stamp the drawn signature onto the master PDF + append an
        audit page, then upload the composite to R2 and persist the
        key on ``proposal.signed_pdf_path``.

        Skipped silently when no master PDF is on file (signature image
        + audit log alone are ESIGN-Act § 7001-compliant). Stamping
        failures are caught and surfaced on ``proposal.signed_pdf_error``
        instead of unwinding acceptance — the operator can re-stamp
        later from the admin UI.
        """
        master_key = proposal.master_contract_pdf_path
        if not master_key or proposal.signature_image is None:
            return

        try:
            master_bytes = await download_object_bytes(master_key)
            stamped = await asyncio.to_thread(
                stamp_master_with_signature,
                StampInputs(
                    master_pdf=master_bytes,
                    signature_png=proposal.signature_image,
                    coords=_coords_for_stamper(
                        proposal.signature_field_coords,
                        field_name="signature",
                    ),
                    date_coords=_coords_for_stamper(
                        proposal.date_field_coords,
                        field_name="date",
                    ),
                    date_label=_signed_date_label(signed_at, signer_timezone),
                    signer_name=proposal.signer_name or "",
                    signer_email=proposal.signer_email or "",
                    signer_ip=signer_ip,
                    signer_user_agent=signer_user_agent,
                    signed_at=signed_at,
                    proposal_number=proposal.proposal_number,
                ),
            )
            timestamp = int(signed_at.timestamp())
            signed_key = f"proposals/{proposal.id}/signed-{timestamp}.pdf"
            await upload_file_bytes(stamped, signed_key, content_type="application/pdf")
            prior_error = proposal.signed_pdf_error
            proposal.signed_pdf_path = signed_key
            proposal.signed_pdf_error = None
            # Commit happens in the ``else`` branch below so the success
            # write lands before unrelated downstream work runs — a flush
            # alone would sit in get_db's outer transaction, and any
            # non-DB exception further down propagates past get_db's
            # narrow (OSError | SQLAlchemyError) handler without
            # triggering rollback, leaving the session closed with the
            # success write uncommitted.
        except PdfReadError as exc:
            logger.exception(
                "Master PDF unreadable for proposal %s", proposal.id,
            )
            proposal.signed_pdf_error = (
                f"Master PDF is corrupt or unreadable: {str(exc)[:900]}"
            )
            await self._commit_stamp_capture(proposal.id)
        except ClientError as exc:
            logger.exception(
                "R2 storage error stamping signed PDF for proposal %s",
                proposal.id,
            )
            response = getattr(exc, "response", None)
            err = response.get("Error", {}) if isinstance(response, dict) else {}
            code = err.get("Code", "ClientError")
            message = err.get("Message", str(exc))
            proposal.signed_pdf_error = (
                f"Object storage temporarily unavailable ({code}): {message}"[:1000]
            )
            await self._commit_stamp_capture(proposal.id)
        except Exception as exc:
            logger.exception(
                "Failed to stamp/upload signed PDF for proposal %s",
                proposal.id,
            )
            proposal.signed_pdf_error = str(exc)[:1000]
            await self._commit_stamp_capture(proposal.id)
        else:
            # Success path — commit the prior_error clear + signed_pdf_path
            # write so the operator-visible state persists regardless of
            # what happens downstream in the accept flow.
            await self._commit_stamp_capture(proposal.id)
            if prior_error:
                logger.info(
                    "Signed PDF re-stamp succeeded for proposal %s "
                    "(cleared error: %r)",
                    proposal.id, prior_error[:200],
                )

    async def _commit_stamp_capture(self, proposal_id: int) -> None:
        """Persist a fail-soft stamp result (success or error-capture)
        before unrelated downstream work runs. Wrapped so a commit
        failure is logged but doesn't unwind the accept itself."""
        try:
            await self.db.commit()
        except Exception:
            logger.exception(
                "Failed to commit stamp capture for proposal %s; the "
                "operator-visible signed_pdf_path/signed_pdf_error may "
                "not surface until the request transaction closes",
                proposal_id,
            )

    async def restamp_signed_pdf(self, proposal: Proposal) -> Proposal:
        """Re-run the fail-soft stamp path; guards prevent post-dating
        an unsigned proposal or stamping without a master PDF."""
        if proposal.status not in ("accepted", "awaiting_payment", "paid"):
            raise ValueError(
                "Only signed proposals can be re-stamped "
                f"(status='{proposal.status}')",
            )
        documents = await self.list_signing_documents(proposal.id)
        if not documents and not proposal.master_contract_pdf_path:
            raise ValueError(
                "Proposal has no signing document PDF to stamp",
            )
        if proposal.signature_image is None:
            raise ValueError(
                "Proposal has no captured signature image",
            )
        if proposal.signed_at is None:
            raise ValueError(
                "Proposal has no recorded signed_at timestamp",
            )

        await self.validate_signing_documents_ready(proposal, require_date=False)
        await self._maybe_stamp_signing_documents(
            proposal,
            signer_ip=proposal.signer_ip,
            signer_user_agent=proposal.signer_user_agent,
            signed_at=proposal.signed_at,
            signer_timezone=proposal.signer_timezone,
        )
        await self.db.refresh(proposal)
        return proposal

    async def reject_proposal_public(
        self,
        proposal: Proposal,
        reason: str | None = None,
        signer_ip: str | None = None,
        signer_user_agent: str | None = None,
        signer_email: str | None = None,
    ) -> Proposal:
        """Reject a proposal via the public link.

        Validates the signer_email against the designated or contact
        email, same as accept. Without this check, anyone who received a
        forwarded copy of the proposal link could permanently reject it.
        """
        if proposal.status not in ("sent", "viewed"):
            raise ValueError(f"Cannot reject proposal in '{proposal.status}' status")

        _assert_signer_matches(proposal, signer_email)

        now = datetime.now(UTC)
        proposal.status = "rejected"
        proposal.rejected_at = now
        proposal.rejection_reason = reason
        proposal.signer_ip = signer_ip
        proposal.signer_user_agent = signer_user_agent
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def record_view(
        self, proposal_id: int, ip_address: str | None = None, user_agent: str | None = None
    ) -> Proposal:
        """Record a view on a proposal and increment view_count."""
        proposal = await self.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        view = ProposalView(
            proposal_id=proposal_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(view)

        now = datetime.now(UTC)
        proposal.view_count = (proposal.view_count or 0) + 1
        proposal.last_viewed_at = now

        # Auto-transition from sent to viewed
        if proposal.status == "sent":
            proposal.status = "viewed"
            proposal.viewed_at = now

        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def get_public_proposal(self, token: str) -> Proposal | None:
        """Get a proposal by its unguessable public token.

        Token-based lookup replaces the old sequential proposal_number
        enumeration. Caller should also use hmac.compare_digest on the
        returned row's public_token before trusting it.
        """
        if not token or len(token) < 16:
            return None
        query = (
            select(Proposal)
            .options(
                selectinload(Proposal.contact),
                selectinload(Proposal.company),
                selectinload(Proposal.signing_documents),
                selectinload(Proposal.bundle),
            )
            .where(Proposal.public_token == token)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def send_proposal_email(
        self, proposal_id: int, user_id: int, attach_pdf: bool = False
    ) -> None:
        """Send branded proposal email to the contact's email."""
        # Pre-flight: queue path swallows GmailNotConnected and parks the
        # row in retry, leaving "sent" UX with no email actually sent.
        await assert_gmail_connected(self.db, user_id)

        proposal = await self.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        if proposal.proposal_bundle_id and proposal.bundle and proposal.bundle.status in {"draft", "sent", "viewed"}:
            raise ValueError("Send the proposal bundle instead of sending one bundled proposal")
        await self.validate_signing_documents_ready(proposal)
        if not proposal.contact_id:
            raise ValueError("Proposal has no associated contact")

        from src.contacts.models import Contact  # noqa: PLC0415
        contact_result = await self.db.execute(
            select(Contact).where(Contact.id == proposal.contact_id)
        )
        contact = contact_result.scalar_one_or_none()
        if not contact or not contact.email:
            raise ValueError("Contact has no email address")

        branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)

        # Build public view URL using the unguessable token (not
        # proposal_number, which is enumerable). Mint one on the fly
        # for pre-migration rows.
        if not proposal.public_token:
            proposal.public_token = secrets.token_urlsafe(32)
            await self.db.flush()
        base_url = settings.FRONTEND_BASE_URL or "http://localhost:3000"
        view_url = f"{base_url}/proposals/public/{proposal.public_token}"

        proposal_data = {
            "proposal_title": proposal.title,
            "client_name": contact.first_name if hasattr(contact, "first_name") else str(contact),
            "summary": proposal.executive_summary or proposal.content or "",
            "view_url": view_url,
        }
        subject, html_body = render_proposal_email(branding, proposal_data)

        attachments: list[EmailAttachment] | None = None
        if attach_pdf:
            try:
                pdf_bytes = await self.generate_proposal_pdf(
                    proposal_id, user_id, include_signature=bool(proposal.signed_at),
                )
            except Exception as exc:
                logger.warning(
                    "PDF render failed for proposal %s — sending email without attachment: %s",
                    proposal_id, exc,
                )
            else:
                suffix = "-signed" if proposal.signed_at else ""
                attachments = [EmailAttachment(
                    filename=f"proposal-{proposal.proposal_number}{suffix}.pdf",
                    content=pdf_bytes,
                    content_type="application/pdf",
                )]

        email_service = EmailService(self.db)
        await email_service.queue_email(
            to_email=contact.email,
            subject=subject,
            body=html_body,
            sent_by_id=user_id,
            entity_type="proposals",
            entity_id=proposal.id,
            attachments=attachments,
        )

        # Mark proposal as sent
        if proposal.status == "draft":
            proposal.status = "sent"
            proposal.sent_at = datetime.now(UTC)
            await self.db.flush()
            await self.db.refresh(proposal)

    async def generate_proposal_pdf(
        self,
        proposal_id: int,
        user_id: int,
        include_signature: bool = False,
    ) -> bytes:
        """Generate a branded proposal PDF in the corporate-professional
        aesthetic that mirrors the public web view.

        When ``include_signature`` is True and the proposal has been
        signed, the PDF includes a signature section with the full
        e-signature audit (name, email, IP, user-agent, timestamp).

        PDF-specific notes:
        - Uses <table> layout instead of flexbox (weasyprint's flex
          has page-fragmentation bugs — issues #2076 + #2163).
        - Omits `text-wrap: balance/pretty` (weasyprint ignores them),
          uses `max-width` constraints on prose blocks instead.
        - Plain business-document styling: clean sans throughout,
          section titles with a short accent rule, no § numbering or
          editorial drama.
        """
        proposal = await self.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)

        company_name_raw = branding.get("company_name") or "CRM"
        company_name = escape(company_name_raw)
        accent = escape(branding.get("primary_color") or "#6366f1")
        footer_text = branding.get("footer_text") or ""

        # Pre-validate the logo URL: if it fails the SSRF check, omit the
        # <img> entirely rather than handing weasyprint a URL it will
        # later refuse and log as an error per page render.
        logo_html = ""
        logo_is_image = False
        logo_url = branding.get("logo_url") or ""
        if logo_url:
            try:
                validate_public_url(
                    logo_url,
                    allowed_schemes=("https",),
                    allowed_hostnames=pdf_logo_allowed_hosts(),
                )
                logo_html = (
                    f'<img src="{escape(logo_url)}" alt="{company_name}" class="letterhead-logo" />'
                )
                logo_is_image = True
            except UnsafeUrlError as exc:
                logger.warning(
                    "Skipping proposal logo for tenant user %s: %s", user_id, exc
                )
        if not logo_html:
            initial = escape((company_name_raw or "P")[0].upper())
            logo_html = f'<span class="letterhead-initial">{initial}</span>'

        # When the uploaded logo is an image that already contains the
        # wordmark (common case for branded PNG/SVG marks), suppress
        # the text company name to avoid "Link Creative  Link Creative".
        letterhead_company_html = (
            "" if logo_is_image else f'<span class="letterhead-company">{company_name}</span>'
        )

        # ---------- Title / cover metadata ----------
        contact_name = ""
        if proposal.contact:
            contact_name = getattr(proposal.contact, "full_name", "") or ""

        secondary_company = ""
        if proposal.company and getattr(proposal.company, "name", None):
            _cname = proposal.company.name  # type: ignore[assignment]
            if _cname and _cname != company_name_raw:
                secondary_company = _cname

        valid_html = ""
        if proposal.valid_until:
            date_str = proposal.valid_until.strftime("%B %d, %Y")
            label = "Expired" if proposal.valid_until < datetime.now(UTC).date() else "Valid until"
            valid_html = (
                f'<p class="cover-validity">{escape(label)} '
                f'<span class="tabular">{escape(date_str)}</span></p>'
            )

        # ---------- Content sections ----------
        section_data = [
            ("Executive Summary", proposal.executive_summary),
            ("Scope of Work", proposal.scope_of_work),
            ("Timeline", proposal.timeline),
            ("Terms & Conditions", proposal.terms),
        ]
        populated_content = [(t, c) for t, c in section_data if c]

        sections_html = ""

        def _section(title_text: str, body_html: str) -> str:
            return (
                '<section class="doc-section">'
                f'  <div class="doc-section-rule"></div>'
                f'  <h2 class="doc-section-title">{title_text}</h2>'
                f'  {body_html}'
                '</section>'
            )

        for title, content in populated_content:
            sections_html += _section(
                escape(title),
                f'<p class="doc-prose">{escape(content)}</p>',
            )

        # Pricing notes stay as authored text; proposal amount/currency fields
        # are no longer rendered on new customer-facing proposal artifacts.
        pricing_free_text = proposal.pricing_section
        if pricing_free_text:
            sections_html += _section(
                "Pricing Notes",
                f'<p class="doc-prose">{escape(pricing_free_text)}</p>',
            )

        legacy_payment_snapshot_html = ""
        if (
            include_signature
            and proposal.signed_at
            and proposal.amount is not None
            and (
                proposal.status in ("awaiting_payment", "paid")
                or bool(proposal.stripe_payment_url)
                or proposal.paid_at is not None
            )
        ):
            try:
                amount_val = Decimal(str(proposal.amount))
            except (ArithmeticError, ValueError, TypeError):
                amount_val = None  # type: ignore[assignment]
            if amount_val is not None and amount_val > 0:
                currency = escape((proposal.currency or "USD").upper())
                legacy_payment_snapshot_html = _section(
                    "Payment Link Record",
                    (
                        '<p class="doc-prose">'
                        "This signed copy preserves the payment amount from "
                        f"the issued legacy payment link: {currency} {amount_val:,.2f}."
                        "</p>"
                    ),
                )
                sections_html += legacy_payment_snapshot_html

        # Fallback `content` block if nothing structured was filled in
        if (
            proposal.content
            and not populated_content
            and not pricing_free_text
            and not legacy_payment_snapshot_html
        ):
            sections_html += _section(
                "Proposal",
                f'<p class="doc-prose">{escape(proposal.content)}</p>',
            )

        # ---------- Cover letter (under the title block) ----------
        cover_letter_html = ""
        if proposal.cover_letter:
            cover_letter_html = (
                '<section class="doc-cover-letter">'
                f"<p>{escape(proposal.cover_letter)}</p>"
                "</section>"
            )

        # ---------- Signatory section ----------
        signatory_html = ""
        if include_signature and proposal.signed_at:
            signed_display = proposal.signed_at.strftime("%B %d, %Y · %H:%M UTC")
            ua = proposal.signer_user_agent or ""
            if len(ua) > 90:
                ua = ua[:87] + "..."

            rows = [
                ("Signatory", proposal.signer_name or ""),
                ("Email", proposal.signer_email or ""),
                ("Signed at", signed_display),
            ]
            if proposal.signer_ip:
                rows.append(("IP address", proposal.signer_ip))
            if ua:
                rows.append(("User-agent", ua))

            rows_html = "".join(
                f'<tr><th>{escape(label)}</th><td class="tabular">{escape(val)}</td></tr>'
                for label, val in rows
            )

            signatory_html = f"""
<section class="doc-signatory page-break-before">
  <div class="doc-section-rule"></div>
  <h2 class="doc-section-title">Signatory</h2>
  <p class="doc-prose">
    This proposal was accepted and electronically signed under the US ESIGN Act
    (15 USC §7001) and applicable state UETA statutes. The signature below
    carries the same legal effect as a handwritten signature.
  </p>
  <table class="doc-signatory-table">
    <tbody>{rows_html}</tbody>
  </table>
  <div class="doc-signature-line"></div>
  <p class="doc-signature-caption">Signed electronically for {escape(proposal.signer_name or "")}</p>
</section>
"""

        # ---------- Assemble ----------
        title_html = escape(proposal.title)
        proposal_number_html = escape(proposal.proposal_number)
        contact_block = (
            f'<p class="cover-prepared-for">Prepared for <strong>{escape(contact_name)}</strong>'
            + (
                f' &middot; <span class="cover-company">{escape(secondary_company)}</span>'
                if secondary_company
                else ""
            )
            + "</p>"
            if contact_name
            else ""
        )
        footer_block = (
            f'<footer class="doc-footer"><p>{escape(footer_text)}</p></footer>'
            if footer_text
            else ""
        )

        html = f"""\
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<style>
  @page {{
    size: Letter;
    margin: 20mm 20mm 20mm 20mm;
  }}
  * {{ box-sizing: border-box; }}
  html {{ font-size: 11pt; }}
  body {{
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #111827;
    line-height: 1.6;
    margin: 0;
    padding: 0;
  }}
  .tabular {{ font-variant-numeric: tabular-nums; }}

  /* ---------- Letterhead ---------- */
  .letterhead {{
    width: 100%;
    border-bottom: 0.75pt solid #e5e7eb;
    margin-bottom: 24pt;
    padding-bottom: 10pt;
  }}
  .letterhead td {{ vertical-align: middle; }}
  .letterhead td.right {{ text-align: right; }}
  .letterhead-logo {{ height: 22pt; width: auto; max-width: 140pt; }}
  .letterhead-initial {{
    display: inline-block;
    width: 20pt; height: 20pt; line-height: 20pt;
    text-align: center;
    background: {accent};
    color: #ffffff;
    font-size: 10pt;
    font-weight: 600;
    margin-right: 8pt;
    vertical-align: middle;
  }}
  .letterhead-company {{
    font-size: 11pt;
    font-weight: 600;
    color: #111827;
    vertical-align: middle;
  }}
  .letterhead-meta {{
    font-size: 9pt;
    color: #6b7280;
  }}

  /* ---------- Cover title block (left-aligned, business-document) ---------- */
  .cover {{
    padding: 0 0 20pt;
    border-bottom: 0.5pt solid #e5e7eb;
    margin-bottom: 24pt;
  }}
  .cover-eyebrow {{
    font-size: 8.5pt;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #6b7280;
    margin: 0 0 8pt;
  }}
  .cover-title {{
    font-weight: 600;
    font-size: 24pt;
    line-height: 1.2;
    letter-spacing: -0.01em;
    color: #0f172a;
    margin: 0 0 10pt;
    max-width: 32em;
  }}
  .cover-prepared-for {{
    font-size: 11pt;
    color: #374151;
    margin: 0 0 4pt;
  }}
  .cover-prepared-for strong {{ font-weight: 600; color: #111827; }}
  .cover-company {{ color: #6b7280; }}
  .cover-validity {{
    font-size: 9pt;
    color: #6b7280;
    margin: 8pt 0 0;
  }}

  /* ---------- Cover letter ---------- */
  .doc-cover-letter {{
    font-size: 11pt;
    line-height: 1.7;
    color: #374151;
    margin: 0 0 24pt;
    max-width: 44em;
  }}
  .doc-cover-letter p {{ margin: 0; white-space: pre-wrap; }}

  /* ---------- Sections ---------- */
  .doc-section {{
    margin: 0 0 24pt;
    page-break-inside: avoid;
  }}
  .doc-section-rule {{
    width: 24pt;
    height: 1.5pt;
    background: {accent};
    margin-bottom: 8pt;
  }}
  .doc-section-title {{
    font-size: 14pt;
    font-weight: 600;
    letter-spacing: -0.01em;
    color: #111827;
    margin: 0 0 10pt;
    line-height: 1.3;
  }}
  .doc-prose {{
    font-size: 10.5pt;
    line-height: 1.7;
    color: #374151;
    margin: 0 0 10pt;
    white-space: pre-wrap;
    max-width: 44em;
  }}

  .pkg-card {{
    border: 0.75pt solid #d1d5db;
    padding: 12pt;
    margin: 0 0 12pt;
    page-break-inside: avoid;
  }}
  .pkg-card h3 {{
    font-size: 12pt;
    margin: 0 0 4pt;
    color: #111827;
  }}
  .pkg-recommended {{
    font-size: 8pt;
    color: #065f46;
    font-weight: 600;
  }}
  .pkg-total {{
    font-size: 11pt;
    font-weight: 600;
    margin: 0 0 6pt;
  }}
  .pkg-desc {{
    font-size: 9.5pt;
    color: #4b5563;
    margin: 0 0 8pt;
  }}
  .pkg-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 9pt;
  }}
  .pkg-table th,
  .pkg-table td {{
    text-align: left;
    padding: 5pt 0;
    border-bottom: 0.5pt solid #e5e7eb;
  }}
  .pkg-table th {{
    color: #6b7280;
    font-weight: 500;
  }}

  /* ---------- Signatory section ---------- */
  .page-break-before {{ page-break-before: always; }}
  .doc-signatory-table {{
    width: 100%;
    max-width: 44em;
    border-collapse: collapse;
    margin: 14pt 0 18pt;
  }}
  .doc-signatory-table th,
  .doc-signatory-table td {{
    text-align: left;
    padding: 7pt 0;
    border-bottom: 0.5pt solid #e5e7eb;
    vertical-align: top;
  }}
  .doc-signatory-table th {{
    font-size: 9pt;
    color: #6b7280;
    font-weight: 500;
    width: 28%;
  }}
  .doc-signatory-table td {{
    font-size: 10pt;
    color: #111827;
    word-break: break-word;
  }}
  .doc-signature-line {{
    width: 50%;
    height: 0.75pt;
    background: #d1d5db;
    margin: 24pt 0 6pt;
  }}
  .doc-signature-caption {{
    font-size: 9pt;
    color: #6b7280;
    margin: 0;
  }}

  .doc-footer {{
    margin-top: 32pt;
    padding-top: 12pt;
    border-top: 0.5pt solid #e5e7eb;
    font-size: 8.5pt;
    color: #9ca3af;
    line-height: 1.5;
  }}
</style>
</head>
<body>
  <table class="letterhead" cellpadding="0" cellspacing="0"><tr>
    <td>{logo_html}{letterhead_company_html}</td>
    <td class="right letterhead-meta tabular">{proposal_number_html}</td>
  </tr></table>

  <section class="cover">
    <p class="cover-eyebrow">Proposal &middot; <span class="tabular">{proposal_number_html}</span></p>
    <h1 class="cover-title">{title_html}</h1>
    {contact_block}
    {valid_html}
  </section>

  {cover_letter_html}
  {sections_html}
  {signatory_html}

  {footer_block}
</body></html>"""

        # Shared renderer enforces the SSRF allowlist on every resource
        # weasyprint tries to load (logo, font, CSS) so a tenant cannot
        # point the renderer at internal IPs or ``file://`` paths.
        return await render_html_to_pdf(html)

    async def send_signed_copy_to_client(self, proposal: Proposal) -> None:
        """Email the client a PDF of the accepted proposal with their e-signature.

        Sent via ``EmailService.queue_email(sent_by_id=proposal.owner_id)`` so
        it routes through the proposal owner's Gmail OAuth connection when
        they have one — otherwise falls back to the tenant's default email
        sender. Failure is logged but does not unwind acceptance.
        """
        if not proposal.signed_at:
            return
        signer_email = (proposal.signer_email or "").strip()
        if not signer_email:
            logger.warning(
                "Cannot send signed copy for proposal %s: no signer email",
                proposal.id,
            )
            return

        branding = await self.get_branding_for_proposal(proposal)
        subject, body = render_contract_signed_email(
            branding,
            {
                "audience": "signer",
                "document_title": proposal.title,
                "signer_name": proposal.signer_name,
            },
        )

        # Render + queue are both best-effort: a failure in either leaves
        # the proposal accepted but without a signed-copy email. The CRM
        # user can resend from the admin UI.
        try:
            # Prefer the stamped master service agreement (the legally
            # executed document the signer expects to receive) over the
            # branded HTML→PDF summary. The HTML version is still useful
            # as a cover page when no master is on file. R2 failures
            # fall back to the generated PDF so a transient storage blip
            # doesn't silently strip the attachment.
            attachments: list[EmailAttachment] = []
            stamped_attached = False
            missing_signed_lines: list[str] = []
            signing_documents = await self.list_signing_documents(proposal.id)
            if signing_documents:
                for document in signing_documents:
                    if not document.signed_pdf_path:
                        missing_signed_lines.append(
                            f"{document.original_filename} (signed copy not generated)",
                        )
                        continue
                    try:
                        stamped_bytes = await download_object_bytes(
                            document.signed_pdf_path,
                        )
                        attachments.append(
                            EmailAttachment(
                                filename=(
                                    f"{proposal.proposal_number}-signed-"
                                    f"{document.original_filename}"
                                ),
                                content=stamped_bytes,
                                content_type="application/pdf",
                            )
                        )
                        stamped_attached = True
                    except Exception as exc:
                        logger.warning(
                            "Failed to fetch signed-PDF object %r for proposal %s "
                            "document %s; signer email will note the missing file",
                            document.signed_pdf_path,
                            proposal.id,
                            document.id,
                            exc_info=True,
                        )
                        document.signed_pdf_error = (
                            "Signed copy could not be loaded from storage at "
                            "email-send time; ask the proposal owner to re-stamp "
                            f"and resend. ({str(exc)[:400]})"
                        )[:1000]
                        missing_signed_lines.append(
                            f"{document.original_filename} (signed copy unavailable)",
                        )
                if missing_signed_lines:
                    try:
                        await self.db.commit()
                    except Exception:
                        logger.exception(
                            "Failed to commit signed-document error capture for "
                            "proposal %s; banner may not surface",
                            proposal.id,
                        )
            elif proposal.signed_pdf_path:
                try:
                    stamped_bytes = await download_object_bytes(
                        proposal.signed_pdf_path,
                    )
                    attachments.append(
                        EmailAttachment(
                            filename=f"proposal-{proposal.proposal_number}-signed.pdf",
                            content=stamped_bytes,
                            content_type="application/pdf",
                        )
                    )
                    stamped_attached = True
                except Exception as exc:
                    # Non-fatal — the generated PDF below keeps the email
                    # useful even when R2 is unreachable. We also stamp
                    # ``signed_pdf_error`` so the operator-visible amber
                    # banner on the proposal detail page picks this up:
                    # without it, the signer would receive the HTML cover
                    # PDF instead of the legally executed master with no
                    # operator-visible signal. Commit (not flush) so the
                    # capture survives even if queue_email below raises.
                    logger.warning(
                        "Failed to fetch signed-PDF object %r for proposal %s; "
                        "falling back to generated copy",
                        proposal.signed_pdf_path,
                        proposal.id,
                        exc_info=True,
                    )
                    proposal.signed_pdf_error = (
                        "Signed copy could not be loaded from storage at "
                        "email-send time; the signer received a fallback "
                        f"copy. Re-stamp to reissue. ({str(exc)[:400]})"
                    )[:1000]
                    try:
                        await self.db.commit()
                    except Exception:
                        logger.exception(
                            "Failed to commit signed_pdf_error capture for "
                            "proposal %s; banner may not surface",
                            proposal.id,
                        )

            if not stamped_attached:
                pdf_bytes = await self.generate_proposal_pdf(
                    proposal.id,
                    proposal.owner_id or 0,
                    include_signature=True,
                )
                attachments.append(
                    EmailAttachment(
                        filename=f"proposal-{proposal.proposal_number}-signed.pdf",
                        content=pdf_bytes,
                        content_type="application/pdf",
                    )
                )

            extra_attachments, missing_lines = await self._collect_proposal_attachments(
                proposal,
            )
            attachments.extend(extra_attachments)
            missing_lines = missing_signed_lines + missing_lines

            final_body = body
            if missing_lines:
                # When an attachment can't be fetched (R2 outage, key
                # rotation, network blip), don't silently drop it from the
                # email — list the filename + sha256 of the stored object
                # key so the recipient can ask the CRM user to resend the
                # missing doc.
                appendix = (
                    "<p><em>Some referenced documents could not be attached "
                    "automatically. Please ask your point of contact to send "
                    "them separately:</em></p><ul>"
                    + "".join(f"<li>{line}</li>" for line in missing_lines)
                    + "</ul>"
                )
                final_body = final_body.replace("</body>", appendix + "</body>", 1)

            email_service = EmailService(self.db)
            await email_service.queue_email(
                to_email=signer_email,
                subject=subject,
                body=final_body,
                sent_by_id=proposal.owner_id,
                entity_type="proposals",
                entity_id=proposal.id,
                attachments=attachments,
            )
        except Exception as exc:
            # exc_info=True forces a full traceback into the log
            # stream. Without it we burned a cycle in 2026-04-24 with a
            # silent signed-copy failure that looked identical between
            # "pod rolled mid-accept" and "PDF template tripped
            # weasyprint" — the traceback is what separates them.
            logger.warning(
                "Failed to send signed copy for proposal %s: %s",
                proposal.id,
                exc,
                exc_info=True,
            )

    async def _collect_proposal_attachments(
        self,
        proposal: Proposal,
    ) -> tuple[list[EmailAttachment], list[str]]:
        """Fetch every staff-uploaded attachment for ``proposal`` from R2.

        Returns ``(attachments, missing_lines)``:
          * ``attachments`` — successfully-fetched files ready to attach.
          * ``missing_lines`` — human-readable "filename + sha256(key)"
            lines for items that failed to download. Caller appends
            these to the email body so the signer at least knows what
            was supposed to be attached.

        File reads use a 10s timeout so a hung R2 endpoint can't stall
        the accept flow indefinitely.
        """
        result = await self.db.execute(
            select(Attachment)
            .where(Attachment.entity_type == "proposals")
            .where(Attachment.entity_id == proposal.id)
            .order_by(Attachment.created_at.asc())
        )
        rows = list(result.scalars().all())
        if not rows:
            return [], []

        att_service = AttachmentService(self.db)
        attachments: list[EmailAttachment] = []
        missing: list[str] = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            for att in rows:
                try:
                    download_url = await att_service.get_download_url(att)
                    if download_url:
                        resp = await client.get(download_url)
                        resp.raise_for_status()
                        content = resp.content
                    else:
                        # Local-disk fallback (dev/test): read the file
                        # straight off the upload directory.
                        path = att_service.get_file_path(att)
                        if not path or not path.exists():
                            raise FileNotFoundError(str(path))
                        content = path.read_bytes()

                    attachments.append(
                        EmailAttachment(
                            filename=att.original_filename,
                            content=content,
                            content_type=att.mime_type or "application/octet-stream",
                        )
                    )
                except (httpx.HTTPError, OSError) as exc:
                    # Narrow catch — programming errors (AttributeError /
                    # TypeError) should crash loudly in tests, not silently
                    # degrade the email body. exc_info=True so the 2am
                    # debug session has a frame, not a one-liner.
                    key_for_hash = att.file_path or att.filename or ""
                    digest = hashlib.sha256(key_for_hash.encode("utf-8")).hexdigest()[:16]
                    logger.warning(
                        "Failed to attach proposal attachment %s (proposal=%s): %s",
                        att.id,
                        proposal.id,
                        exc,
                        exc_info=True,
                    )
                    missing.append(f"{att.original_filename} (ref {digest})")

        return attachments, missing

    async def get_effective_terms_and_conditions(
        self,
        proposal: Proposal,
    ) -> str | None:
        """Resolve the T&C body rendered in the Sign-to-Confirm modal.

        Per-proposal override always wins; falls back to the tenant
        default. Returns ``None`` when neither is set so the modal
        can omit the T&C card entirely rather than render an empty
        scroll box.
        """
        if proposal.terms_and_conditions:
            return proposal.terms_and_conditions
        if not proposal.owner_id:
            return None
        from src.whitelabel.models import Tenant, TenantSettings, TenantUser  # noqa: PLC0415

        # Prefer the user's primary tenant but fall back to ANY
        # membership when no row carries is_primary=True. The strict
        # is_primary filter silently served the generic defaults on
        # PR #114 (see feedback_tenant_branding_is_primary) — same
        # JOIN shape, same trap, applied here to the T&C body.
        result = await self.db.execute(
            select(TenantSettings.default_terms_and_conditions)
            .join(Tenant, Tenant.id == TenantSettings.tenant_id)
            .join(TenantUser, TenantUser.tenant_id == Tenant.id)
            .where(TenantUser.user_id == proposal.owner_id)
            .order_by(TenantUser.is_primary.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def upload_master_contract_pdf(
        self,
        proposal: Proposal,
        content: bytes,
        filename: str,
    ) -> Proposal:
        """Persist the rep-uploaded master service agreement PDF.

        Stored at ``proposals/{id}/master.pdf`` in R2. Replacing an
        existing master simply overwrites the same key — the old
        object is orphaned but the next signing run reads only the
        path on the row, so there's no consistency issue.
        """
        if not content:
            raise ValueError("master PDF is empty")
        # Lightweight magic-byte sniff so a mis-uploaded .docx doesn't
        # blow up later inside the pypdf parser with an opaque error.
        if not content.startswith(b"%PDF-"):
            raise ValueError("master contract must be a PDF file")
        # 25 MB hard cap; matches the typical attachment ceiling on
        # the platform's R2 bucket. Audit + stamping load this into
        # memory so an unbounded upload could OOM the pod.
        if len(content) > 25 * 1024 * 1024:
            raise ValueError("master contract exceeds 25 MB limit")
        key = f"proposals/{proposal.id}/master.pdf"
        await upload_file_bytes(content, key, content_type="application/pdf")
        proposal.master_contract_pdf_path = key
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def get_branding_for_proposal(self, proposal: Proposal) -> dict:
        """Get tenant branding from the proposal owner's tenant."""
        if proposal.owner_id:
            return await TenantBrandingHelper.get_branding_for_user(self.db, proposal.owner_id)
        return TenantBrandingHelper.get_default_branding()

    async def substitute_template_variables(self, template_content: str, variables: dict) -> str:
        """Replace {{variable}} placeholders in template content.

        Single-pass substitution so a value that itself contains ``{{x}}``
        is not re-expanded. Missing keys are left as-is; present-but-falsy
        values (None, empty string) substitute to an empty string.
        """

        def _replacer(match: "re.Match[str]") -> str:
            key = match.group(1)
            if key not in variables:
                return match.group(0)
            value = variables[key]
            return str(value) if value else ""

        return _TEMPLATE_VAR_PATTERN.sub(_replacer, template_content)


class ProposalTemplateService(BaseService[ProposalTemplate]):
    """Service for ProposalTemplate read operations. Create/update live in the router."""

    model = ProposalTemplate

    async def get_list(
        self,
        category: str | None = None,
    ) -> list[ProposalTemplate]:
        """Get all templates, optionally filtered by category."""
        query = select(ProposalTemplate)
        if category:
            query = query.where(ProposalTemplate.category == category)
        query = query.order_by(ProposalTemplate.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

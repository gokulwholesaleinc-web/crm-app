"""Shared helpers for the public + download routers.

Token→packet resolution (with lazy expiry + scrub), bearer-session checks,
and request-body abuse caps. Kept separate so both router files stay thin.
"""

from __future__ import annotations

import base64
import binascii
from typing import TypeVar

from fastapi import HTTPException, Request
from pydantic import BaseModel, ValidationError

from src.core.constants import HTTPStatus
from src.onboarding import tokens
from src.onboarding.models import OnboardingPacket
from src.onboarding.packet_errors import PacketGoneError

_BodyModel = TypeVar("_BodyModel", bound=BaseModel)

# Cache-Control + Referrer-Policy applied to every public bytes/JSON response
# that may carry recipient PII (signed PDFs, the source PDF, the post-gate
# field_values JSON). Shared by the public + download routers (one source).
NO_STORE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}

# Re-exported for the download router's expiry check (single UTC-now source).
from src.onboarding.packet_service import (
    DEAD_STATUSES,
    PacketService,
    _ensure_aware,  # noqa: F401  (re-exported for the download router)
    _now,  # noqa: F401
    scrub_packet,
)

# Abuse caps (§6).
MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MB JSON body cap on public mutations
MAX_SIGNATURE_BYTES = 200 * 1024
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


async def load_packet_for_public(
    db, token: str
) -> tuple[OnboardingPacket, PacketService]:
    """Resolve a packet by access token, applying lazy expiry.

    Raises 404 on an unknown token, and (after lazily flipping to ``expired``
    + scrubbing) 410 on an expired or otherwise terminal-dead packet. A
    forwarded-but-revoked link 410s too. Constant-time hash compare.
    """
    token_hash = tokens.hash_token(token)
    service = PacketService(db)
    packet = await service.get_by_token_hash(token_hash)
    if packet is None or not tokens.verify_hash(token, packet.token_hash):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Onboarding link not found."
        )

    if packet.status in DEAD_STATUSES:
        raise HTTPException(
            status_code=HTTPStatus.GONE,
            detail="This onboarding link is no longer available.",
        )

    # Lazy expiry: a writable packet past its TTL flips to expired + scrubs.
    # COMMIT (not flush) the flip + PII scrub: this branch raises an
    # HTTPException, which is neither OSError nor SQLAlchemyError, so the
    # ``get_db`` dependency skips its own commit and the ``finally: close()``
    # would otherwise roll the scrub back — leaving the recipient's PII
    # un-scrubbed and the flip recomputed (and re-discarded) on every hit (§12).
    if _ensure_aware(packet.token_expires_at) <= _now() and packet.status not in (
        "completed",
    ):
        documents = await service.load_documents(packet.id)
        packet.status = "expired"
        # Expiry is a non-delivery terminal — full PII purge (delete uploads +
        # secrets), unlike completion which retains the deliverable.
        await scrub_packet(db, packet, documents, purge=True)
        await db.commit()
        raise HTTPException(
            status_code=HTTPStatus.GONE,
            detail="This onboarding link has expired.",
        )
    return packet, service


async def resolve_public_branding(db):
    """Build the sender-brand styling for the public page from TenantSettings.

    The CRM is single-tenant by design, so the one ``TenantSettings`` row is
    the brand source. Returns ``None`` when no settings row exists (the
    frontend then keeps its neutral default branding).
    """
    from sqlalchemy import select

    from src.onboarding.packet_schemas import PublicBranding
    from src.whitelabel.models import TenantSettings

    row = (
        await db.execute(
            select(TenantSettings).order_by(TenantSettings.id).limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return PublicBranding(
        company_name=row.company_name,
        logo_url=row.logo_url,
        primary_color=row.primary_color,
        secondary_color=row.secondary_color,
        accent_color=row.accent_color,
        bg_color_light=row.bg_color_light,
        surface_color_light=row.surface_color_light,
        footer_text=row.footer_text,
        privacy_policy_url=row.privacy_policy_url,
        terms_of_service_url=row.terms_of_service_url,
    )


def require_session(request: Request, packet: OnboardingPacket) -> dict:
    """Validate the X-Onboarding-Session header against this packet → 401 else."""
    raw = request.headers.get("X-Onboarding-Session")
    session = tokens.verify_session(raw)
    if (
        session is None
        or session.get("packet_id") != packet.id
        or session.get("token_hash") != packet.token_hash
    ):
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail="Verify your email to continue.",
        )
    return session


def assert_body_within_caps(request: Request) -> None:
    """Reject missing Content-Length (411) / over-cap body (413) pre-parse."""
    raw_len = request.headers.get("content-length")
    if raw_len is None:
        raise HTTPException(
            status_code=HTTPStatus.LENGTH_REQUIRED,
            detail="Content-Length header is required.",
        )
    try:
        length = int(raw_len)
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.LENGTH_REQUIRED,
            detail="Invalid Content-Length header.",
        ) from exc
    if length > MAX_BODY_BYTES:
        raise HTTPException(
            status_code=HTTPStatus.PAYLOAD_TOO_LARGE,
            detail="Request body is too large.",
        )


async def parse_body_within_caps(
    request: Request, model: type[_BodyModel]
) -> _BodyModel:
    """Read + size-cap + validate a public mutation body BEFORE it is parsed.

    A declared Pydantic body parameter is buffered and parsed by FastAPI during
    dependency resolution — i.e. BEFORE the handler runs — so a header-only cap
    in the handler can't stop a body-parse/memory abuse. Calling this from the
    handler instead reads the raw body with the 1 MB cap genuinely preceding the
    JSON parse (the header cap rejects an honest oversized/absent Content-Length;
    the post-read length check rejects a lying one), then validates against
    ``model`` → 422 on a malformed body.
    """
    assert_body_within_caps(request)
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(
            status_code=HTTPStatus.PAYLOAD_TOO_LARGE,
            detail="Request body is too large.",
        )
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="Invalid request body.",
        ) from exc


def decode_signature_png(signature_png_base64: str) -> bytes:
    """Decode + validate a drawn signature: ≤200 KB and PNG magic bytes (422)."""
    # Cap the base64 length before decoding (base64 inflates ~4/3).
    if len(signature_png_base64) > MAX_SIGNATURE_BYTES * 2:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="Signature image is too large.",
        )
    payload = signature_png_base64.split(",", 1)[-1]  # tolerate data: URI prefix
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="Signature image is not valid base64.",
        ) from exc
    if len(raw) > MAX_SIGNATURE_BYTES:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="Signature image exceeds 200 KB.",
        )
    if not raw.startswith(_PNG_MAGIC):
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="Signature image must be a PNG.",
        )
    # Magic bytes alone don't prove the PNG is decodable — a truncated/corrupt
    # payload (valid header, garbage body) passes the check above but raises
    # OSError when the stamper hands it to reportlab's ImageReader (PIL),
    # surfacing as a completion-time 500. Decode it HERE through the exact same
    # ImageReader so a bad PNG is a clean 422 at the signature step instead.
    import io

    from reportlab.lib.utils import ImageReader

    try:
        ImageReader(io.BytesIO(raw)).getSize()
    except Exception as exc:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="Signature image is not a readable PNG.",
        ) from exc
    return raw


def public_status_message(status: str) -> str:
    """Recipient-facing copy per status (matrix §5.2)."""
    return {
        "active": "Please complete your onboarding documents.",
        "opened": "Please complete your onboarding documents.",
        "in_progress": "Continue completing your onboarding documents.",
        "completing": "Your documents are being finalized.",
        "completed": "Completed — check your email for the download link.",
        "completion_failed": "We're finishing your documents.",
    }.get(status, "This onboarding link is no longer available.")


def gone_if_dead(packet: OnboardingPacket) -> None:
    """Raise 410 if the packet is terminal-dead (used by mutation routes)."""
    if packet.status in DEAD_STATUSES:
        raise PacketGoneError("This onboarding link is no longer available.")


def find_document_or_404(documents, doc_id: int):
    """Return the document with ``doc_id`` from a loaded list, or raise 404."""
    doc = next((d for d in documents if d.id == doc_id), None)
    if doc is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Document not found."
        )
    return doc


async def read_pdf_or_http(path: str) -> bytes:
    """Read a stored PDF, mapping storage errors to 404/503 (never an opaque 500).

    Shared by the session-gated document view and the completion-download
    proxy — both need the identical FileNotFoundError→404 / RuntimeError→503
    translation that ``onboarding.storage.read_bytes`` already normalizes for
    R2 and disk.
    """
    from src.onboarding import storage

    try:
        return await storage.read_bytes(path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Document file missing."
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            detail="Document storage temporarily unavailable.",
        ) from exc

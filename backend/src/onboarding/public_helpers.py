"""Shared helpers for the public + download routers.

Token→packet resolution (with lazy expiry + scrub), bearer-session checks,
and request-body abuse caps. Kept separate so both router files stay thin.
"""

from __future__ import annotations

import base64
import binascii

from fastapi import HTTPException, Request

from src.core.constants import HTTPStatus
from src.onboarding import tokens
from src.onboarding.models import OnboardingPacket
from src.onboarding.packet_errors import PacketGoneError

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
    if _ensure_aware(packet.token_expires_at) <= _now() and packet.status not in (
        "completed",
    ):
        documents = await service.load_documents(packet.id)
        packet.status = "expired"
        scrub_packet(packet, documents)
        await db.flush()
        raise HTTPException(
            status_code=HTTPStatus.GONE,
            detail="This onboarding link has expired.",
        )
    return packet, service


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

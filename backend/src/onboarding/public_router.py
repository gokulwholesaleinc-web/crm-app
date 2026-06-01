"""Public (token-only) + completion-download routes (Phase 2, §3.2/§3.3).

No CRM auth — the access token gates the public flow and a short-lived
HMAC bearer session (``X-Onboarding-Session``) gates the post-email-verify
mutations. Rate-limited per IP. Completion downloads PROXY the bytes (presign
can't set ``Cache-Control``/``Referrer-Policy``).
"""


from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from src.core.client_ip import get_client_ip
from src.core.constants import HTTPStatus
from src.core.rate_limit import limiter
from src.core.router_utils import DBSession
from src.onboarding import completion, tokens
from src.onboarding.packet_schemas import (
    CompleteResponse,
    DocumentPatch,
    PatchResult,
    PublicDocument,
    PublicPacketPostResponse,
    PublicPacketPreResponse,
    SignatureResult,
    SignatureSet,
    VerifyRequest,
    VerifyResponse,
)
from src.onboarding.packet_service import _now as _utc_now
from src.onboarding.public_helpers import (
    NO_STORE_HEADERS,
    assert_body_within_caps,
    decode_signature_png,
    find_document_or_404,
    load_packet_for_public,
    parse_body_within_caps,
    public_status_message,
    read_pdf_or_http,
    require_session,
    resolve_public_branding,
)
from src.onboarding.validation import complete_errors_mapped, packet_errors_mapped
from src.onboarding.view_ledger import record_packet_document_view

router = APIRouter(prefix="/api/onboarding/public", tags=["onboarding-public"])
DB = DBSession


@router.get("/{token}", response_model=None)
@limiter.limit("60/minute")
async def get_public_packet(token: str, request: Request, response: Response, db: DB):
    """Pre-gate branding + counts; post-gate (valid session) full documents."""
    packet, service = await load_packet_for_public(db, token)
    company_name = await service.resolve_company_name(packet)
    branding = await resolve_public_branding(db)
    documents = await service.load_documents(packet.id)

    # The post-gate payload carries recipient field_values (PII) — never cache it.
    response.headers["Cache-Control"] = "no-store"

    session = tokens.verify_session(request.headers.get("X-Onboarding-Session"))
    is_session = (
        session is not None
        and session.get("packet_id") == packet.id
        and session.get("token_hash") == packet.token_hash
    )
    if not is_session or packet.status == "completed":
        return PublicPacketPreResponse(
            status=packet.status,
            document_count=len(documents),
            status_message=public_status_message(packet.status),
            company_name=company_name,
            branding=branding,
        )

    disclosure = None
    disclosure_version = None
    for doc in documents:
        if doc.esign_disclosure_snapshot:
            disclosure = doc.esign_disclosure_snapshot
            disclosure_version = doc.esign_disclosure_version
            break
    return PublicPacketPostResponse(
        status=packet.status,
        document_count=len(documents),
        status_message=public_status_message(packet.status),
        company_name=company_name,
        branding=branding,
        documents=[
            PublicDocument(
                id=d.id,
                original_filename=d.original_filename,
                field_definitions=d.field_definitions or [],
                field_values=d.field_values or {},
                field_values_version=d.field_values_version,
                requires_esign=d.requires_esign,
            )
            for d in documents
        ],
        signature_version=packet.signature_version,
        has_signature=packet.signer_signature_image is not None,
        esign_disclosure=disclosure,
        esign_disclosure_version=disclosure_version,
    )


@router.post("/{token}/verify", response_model=VerifyResponse)
@limiter.limit("20/minute")
async def verify_email(token: str, data: VerifyRequest, request: Request, db: DB):
    """E-mail gate. Generic result (no enumeration) + per-(token,ip) throttle."""
    packet, _ = await load_packet_for_public(db, token)
    client_ip = get_client_ip(request)
    token_hash = packet.token_hash
    if tokens.verify_throttle_blocked(token_hash, client_ip):
        raise HTTPException(
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            detail="Too many attempts; please try again later.",
        )
    import hmac as _hmac

    matches = _hmac.compare_digest(
        str(data.email).strip().lower(),
        (packet.recipient_email or "").strip().lower(),
    )
    if not matches:
        tokens.verify_throttle_record_failure(token_hash, client_ip)
        return VerifyResponse(success=False)

    tokens.reset_throttle(token_hash, client_ip)
    session = tokens.sign_session(
        packet_id=packet.id,
        token_hash=token_hash,
        signer_email=packet.recipient_email,
    )
    return VerifyResponse(
        success=True, session_token=session, expires_in=tokens.SESSION_TTL_SECONDS
    )


@router.get("/{token}/documents/{doc_id}/pdf", response_model=None)
@limiter.limit("60/minute")
async def get_public_document_pdf(
    token: str, doc_id: int, request: Request, db: DB
):
    """Stream a document PDF (session-gated); record the read-before-sign view."""
    packet, service = await load_packet_for_public(db, token)
    require_session(request, packet)
    if packet.status in ("completing", "completed"):
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT, detail="Packet is being finalized."
        )
    documents = await service.load_documents(packet.id)
    doc = find_document_or_404(documents, doc_id)
    content = await read_pdf_or_http(doc.pdf_path)

    # Record the view AFTER bytes are confirmed; first view → opened.
    is_first = await record_packet_document_view(
        db,
        packet_document_id=doc.id,
        token=token,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    if is_first:
        packet.first_opened_at = packet.first_opened_at or _utc_now()
        if packet.status == "active":
            packet.status = "opened"
    await db.flush()
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            **NO_STORE_HEADERS,
            "Content-Disposition": f'inline; filename="{doc.original_filename}"',
        },
    )


@router.patch("/{token}/documents/{doc_id}", response_model=PatchResult)
@limiter.limit("60/minute")
async def patch_public_document(
    token: str, doc_id: int, request: Request, db: DB
):
    """Save field values (session-gated; 409 on version drift)."""
    # Read the body INSIDE the handler so the 1 MB cap precedes the parse
    # (a declared body param is parsed before this runs — see §6).
    data = await parse_body_within_caps(request, DocumentPatch)
    packet, service = await load_packet_for_public(db, token)
    require_session(request, packet)
    documents = await service.load_documents(packet.id)
    doc = find_document_or_404(documents, doc_id)
    with packet_errors_mapped():
        version = await service.patch_document(
            packet, doc, field_values=data.field_values, base_version=data.base_version
        )
    return PatchResult(field_values_version=version)


@router.post("/{token}/signature", response_model=SignatureResult)
@limiter.limit("30/minute")
async def set_public_signature(
    token: str, request: Request, db: DB
):
    """Store the drawn signature (session-gated; 409 on signature drift)."""
    data = await parse_body_within_caps(request, SignatureSet)
    packet, service = await load_packet_for_public(db, token)
    require_session(request, packet)
    signature_png = decode_signature_png(data.signature_png_base64)
    with packet_errors_mapped():
        version = await service.set_signature(
            packet,
            signature_png=signature_png,
            base_signature_version=data.base_signature_version,
        )
    return SignatureResult(signature_version=version)


@router.post("/{token}/complete", response_model=CompleteResponse)
@limiter.limit("10/minute")
async def complete_public_packet(token: str, request: Request, db: DB):
    """Run the 3-phase completion (session-gated)."""
    assert_body_within_caps(request)
    packet, _ = await load_packet_for_public(db, token)
    session = require_session(request, packet)
    with complete_errors_mapped():
        result = await completion.complete_packet(
            db,
            packet=packet,
            access_token=token,
            signer_email=session.get("signer_email", ""),
            signer_ip=get_client_ip(request),
            signer_user_agent=request.headers.get("user-agent"),
        )
    return CompleteResponse(**result)

"""Public (token-only) + completion-download routes (Phase 2, §3.2/§3.3).

No CRM auth — the access token gates the public flow and a short-lived
HMAC bearer session (``X-Onboarding-Session``) gates the post-email-verify
mutations. Rate-limited per IP. Completion downloads PROXY the bytes (presign
can't set ``Cache-Control``/``Referrer-Policy``).
"""


from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from src.core.client_ip import get_client_ip
from src.core.constants import HTTPStatus
from src.core.rate_limit import limiter
from src.core.router_utils import DBSession
from src.onboarding import completion, tokens
from src.onboarding.kinds import get_handler
from src.onboarding.packet_schemas import (
    CompleteResponse,
    ConsentRequest,
    ConsentResult,
    DocumentPatch,
    FileDeleteResult,
    FileUploadResult,
    PatchResult,
    PublicDocument,
    PublicPacketPostResponse,
    PublicPacketPreResponse,
    SignatureResult,
    SignatureSet,
    VerifyRequest,
    VerifyResponse,
    ViewedResult,
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
from src.onboarding.uploads import (
    delete_document_upload,
    store_document_upload,
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
                kind=d.kind,
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
        has_consented=all(
            d.consented_at is not None for d in documents if d.requires_esign
        ),
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
    if doc.pdf_path is None:
        # A questionnaire/upload doc has no PDF stream (v3); the frontend marks
        # it viewed via POST /viewed instead. Never call /pdf on a non-PDF kind.
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="This document has no PDF to view.",
        )
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


@router.post("/{token}/documents/{doc_id}/viewed", response_model=ViewedResult)
@limiter.limit("60/minute")
async def mark_public_document_viewed(
    token: str, doc_id: int, request: Request, db: DB
):
    """Record a read-before-sign view for a NON-PDF document (session-gated).

    The kind-agnostic counterpart of the ``/pdf`` view side effect (P0-4):
    questionnaire and upload_request docs have no PDF stream, so the frontend
    POSTs this on first render of each such doc. It writes the SAME idempotent
    ledger row + the same first-open→``opened`` transition the ``/pdf`` route
    does, so ``_assert_all_viewed`` (unchanged) is satisfied for every kind
    rather than 422-ing forever on a doc with no PDF. esign docs keep recording
    via ``/pdf`` (the legally meaningful record-before-sign). This endpoint
    REFUSES any kind that records via the stream (F1): otherwise a client could
    mark an esign signing-doc viewed without ever loading the PDF, satisfying
    ``_assert_all_viewed`` and bypassing the read-before-sign gate.
    """
    packet, service = await load_packet_for_public(db, token)
    require_session(request, packet)
    if packet.status in ("completing", "completed"):
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT, detail="Packet is being finalized."
        )
    documents = await service.load_documents(packet.id)
    doc = find_document_or_404(documents, doc_id)
    # F1: a kind that records its view via the byte stream (esign /pdf) must NOT
    # be markable through this endpoint — the read-before-sign record only counts
    # when the signer actually loaded the document. Only no-stream kinds
    # (questionnaire/upload_request) use /viewed.
    if get_handler(doc.kind).records_view_via_stream:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Open this document to view it before continuing.",
        )
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
    return ViewedResult(viewed=True, opened=is_first)


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


@router.post(
    "/{token}/documents/{doc_id}/files",
    response_model=FileUploadResult,
    status_code=HTTPStatus.CREATED,
)
@limiter.limit("30/minute")
async def upload_document_file(
    token: str,
    doc_id: int,
    request: Request,
    db: DB,
    field_id: str = Form(...),
    file: UploadFile = File(...),
):
    """Attach one file to a ``file_upload`` field at FILL time (session-gated).

    Lands the file as its own ``contacts`` Attachment + an
    ``onboarding_packet_uploads`` fence row, then appends the upload-row id to
    ``field_values[field_id]`` (P0-6). BYPASSES the version-fence PATCH
    (additive — no lost-update surface). Magic-byte sniff + allow-list +
    per-field maxMB/maxFiles + per-packet aggregate cap are enforced in
    ``store_document_upload`` (→ 422 on any breach). Rejected once the packet is
    being finalized.
    """
    packet, service = await load_packet_for_public(db, token)
    require_session(request, packet)
    if packet.status in ("completing", "completed"):
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT, detail="Packet is being finalized."
        )
    service._assert_public_writable(packet)
    documents = await service.load_documents(packet.id)
    doc = find_document_or_404(documents, doc_id)
    content = await file.read()
    with packet_errors_mapped():
        result = await store_document_upload(
            db,
            packet=packet,
            doc=doc,
            field_id=field_id,
            original_filename=file.filename or "upload",
            content=content,
            token=token,
        )
    await db.flush()
    return result


@router.delete(
    "/{token}/documents/{doc_id}/files/{upload_id}",
    response_model=FileDeleteResult,
)
@limiter.limit("30/minute")
async def delete_document_file(
    token: str, doc_id: int, upload_id: int, request: Request, db: DB
):
    """Remove one uploaded file before completion (session-gated).

    Deletes the Attachment (storage + row via ``delete_attachment``) + the
    fence row and drops the id from ``field_values[field_id]``. Rejected once
    the packet is being finalized.
    """
    packet, service = await load_packet_for_public(db, token)
    require_session(request, packet)
    if packet.status in ("completing", "completed"):
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT, detail="Packet is being finalized."
        )
    service._assert_public_writable(packet)
    documents = await service.load_documents(packet.id)
    doc = find_document_or_404(documents, doc_id)
    with packet_errors_mapped():
        result = await delete_document_upload(
            db, doc=doc, upload_id=upload_id
        )
    await db.flush()
    return result


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


@router.post("/{token}/consent", response_model=ConsentResult)
@limiter.limit("30/minute")
async def record_public_consent(token: str, request: Request, db: DB):
    """Record electronic-records consent per e-sign doc (session-gated; §D.1).

    The affirmative consent step the signer makes BEFORE drawing a signature.
    Idempotent. 409 if the echoed ``disclosure_version`` doesn't match the
    stored snapshot. ``/complete`` 422s until this has been recorded.
    """
    data = await parse_body_within_caps(request, ConsentRequest)
    packet, service = await load_packet_for_public(db, token)
    require_session(request, packet)
    with packet_errors_mapped():
        consented = await service.record_consent(
            packet, disclosure_version=data.disclosure_version
        )
    return ConsentResult(consented=True, documents_consented=consented)


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

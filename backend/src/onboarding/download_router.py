"""Completion-download routes (no login) — PROXY bytes, never redirect.

Split out of ``public_router`` to keep that route file under budget. These
routes serve the signed PDFs to the recipient via a short-lived download
token (minted at completion). They proxy the bytes through the app rather
than redirecting to an R2 presign, because the presign can only set
Bucket/Key — it can't set ``Cache-Control``/``Referrer-Policy`` on the
response (``object_storage.py``), and a redirect would leak the token via
``Referer``. Revoking the packet nulls ``download_token_hash`` → 404 here.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select

from src.core.constants import HTTPStatus
from src.core.rate_limit import limiter
from src.core.router_utils import DBSession
from src.onboarding import tokens
from src.onboarding.models import OnboardingPacket
from src.onboarding.packet_schemas import DownloadDocument, DownloadLandingResponse
from src.onboarding.packet_service import PacketService
from src.onboarding.public_helpers import (
    _ensure_aware,
    _now,
    find_document_or_404,
    read_pdf_or_http,
)

download_router = APIRouter(
    prefix="/api/onboarding/download", tags=["onboarding-download"]
)
DB = DBSession

_NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


async def _load_completed_by_download_token(db, download_token: str) -> OnboardingPacket:
    """Resolve a completed packet by download token (hash lookup + expiry)."""
    token_hash = tokens.hash_token(download_token)
    result = await db.execute(
        select(OnboardingPacket).where(
            OnboardingPacket.download_token_hash == token_hash
        )
    )
    packet = result.scalar_one_or_none()
    if (
        packet is None
        or not tokens.verify_hash(download_token, packet.download_token_hash)
        or packet.status != "completed"
    ):
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Download link not found."
        )
    if packet.download_token_expires_at and _ensure_aware(
        packet.download_token_expires_at
    ) <= _now():
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Download link has expired."
        )
    return packet


@download_router.get("/{download_token}", response_model=DownloadLandingResponse)
@limiter.limit("30/minute")
async def download_landing(download_token: str, request: Request, db: DB):
    packet = await _load_completed_by_download_token(db, download_token)
    documents = await PacketService(db).load_documents(packet.id)
    return Response(
        content=DownloadLandingResponse(
            documents=[
                DownloadDocument(
                    doc_id=d.id,
                    title=d.original_filename,
                    url=f"/api/onboarding/download/{download_token}/documents/{d.id}",
                )
                for d in documents
            ]
        ).model_dump_json(),
        media_type="application/json",
        headers=_NO_STORE,
    )


@download_router.get("/{download_token}/documents/{doc_id}", response_model=None)
@limiter.limit("30/minute")
async def download_document(
    download_token: str, doc_id: int, request: Request, db: DB
):
    from src.attachments.service import AttachmentService

    packet = await _load_completed_by_download_token(db, download_token)
    documents = await PacketService(db).load_documents(packet.id)
    doc = find_document_or_404(documents, doc_id)
    if doc.attachment_id is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Document not found."
        )
    attachment = await AttachmentService(db).get_attachment(doc.attachment_id)
    if attachment is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Document not found."
        )
    content = await read_pdf_or_http(attachment.file_path)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            **_NO_STORE,
            "Content-Disposition": f'attachment; filename="{doc.original_filename}"',
        },
    )

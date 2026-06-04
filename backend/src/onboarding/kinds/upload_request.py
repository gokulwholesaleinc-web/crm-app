"""``upload_request`` DocumentType — a file-collection document as a plugin.

The third v3 document kind (§B.3): a flat list of ``file_upload`` questions the
client answers by uploading files at FILL time (via the dedicated
``POST /{token}/documents/{id}/files`` endpoint — NOT the version-fence PATCH).
Each file lands as its own ``contacts`` Attachment immediately and is tracked by
an ``onboarding_packet_uploads`` row, so the document's own 1:1 ``attachment_id``
fence stays reserved for the single completion MANIFEST artifact this handler
produces (a Phase-B retry therefore never duplicates uploaded files — P0-6).

Discipline (§B.1): kind-specific indexing of ``field_definitions`` /
``field_values`` (``field["maxFiles"]``, the upload-row counting) lives ONLY in
this handler — never in the kind-agnostic core.

Leaf module: imports NOTHING from ``src.onboarding.kinds`` (so discovery stays
cycle-free) and only leaf onboarding modules at top level; the heavy deps
(reportlab, the brand header, the attachments service, the models) are
lazy-imported inside the methods where the app graph is already initialized.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.onboarding.packet_errors import PacketValidationError
from src.onboarding.prefill import ALLOWED_PREFILL

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.onboarding.models import OnboardingPacket, OnboardingPacketDocument

# Hard ceilings the author-time validator clamps each field to, so a seeded
# definition can't ask for an absurd per-file cap or file count. The PER-PACKET
# aggregate byte cap and the magic-byte/extension allow-list live on the upload
# ENDPOINT (the actual bytes never reach this handler).
_MAX_FILES_CEILING = 50
_MAX_MB_CEILING = 500


def _human_size(num_bytes: int) -> str:
    """``1536`` → ``"1.5 KB"`` (manifest display only; never security-bearing)."""
    size = float(max(num_bytes, 0))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def validate_upload_definitions(defs: list[dict]) -> None:
    """Author-time check for an upload_request definition (FLAT list, no PDF).

    NEVER reads ``pdf_bytes`` (P0-9: an upload template carries no PDF). Every
    field is a ``file_upload`` with a positive-int ``maxFiles``/``maxMB`` within
    the ceilings; file fields carry no prefill, and any ``prefill`` value is
    still checked against the shared ``ALLOWED_PREFILL`` (never a local copy →
    ``email``/PII can never be made prefillable, §D.5). Ids are unique and match
    the established ``^[a-z0-9_]+$`` identifier shape the other kinds use.
    """
    # Lazy (author-time only) — keeps this module's top-level imports leaf-only.
    from src.onboarding.service import FieldDefinitionError

    if not isinstance(defs, list):
        raise FieldDefinitionError("upload_request fields must be a list")

    seen_ids: set[str] = set()
    for index, field in enumerate(defs):
        if not isinstance(field, dict):
            raise FieldDefinitionError(f"field {index} must be an object")
        label = f"field '{field.get('id', index)}'"

        field_id = field.get("id")
        if not isinstance(field_id, str) or not field_id:
            raise FieldDefinitionError(f"{label}: id is required")
        if field_id in seen_ids:
            raise FieldDefinitionError(f"Duplicate field id '{field_id}'")
        seen_ids.add(field_id)

        if field.get("kind") != "file_upload":
            raise FieldDefinitionError(
                f"{label}: upload_request only supports file_upload fields"
            )

        # A non-empty label is required (rendered on the public upload slot).
        field_label = field.get("label")
        if not isinstance(field_label, str) or not field_label.strip():
            raise FieldDefinitionError(f"{label}: a non-empty label is required")

        # ``required`` must be a REAL bool — a stringy ``"false"`` is truthy at
        # fill time and would silently force the upload.
        if "required" in field and not isinstance(field["required"], bool):
            raise FieldDefinitionError(
                f"{label}: required must be true or false"
            )

        if field.get("prefill") not in (None, *ALLOWED_PREFILL):
            raise FieldDefinitionError(
                f"{label}: unsupported prefill '{field.get('prefill')}'"
            )

        for cap_key, ceiling in (
            ("maxFiles", _MAX_FILES_CEILING),
            ("maxMB", _MAX_MB_CEILING),
        ):
            cap = field.get(cap_key)
            # bool is an int subclass; reject it explicitly so True/False can't
            # masquerade as a 1/0 cap.
            if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
                raise FieldDefinitionError(
                    f"{label}: {cap_key} must be a positive integer"
                )
            if cap > ceiling:
                raise FieldDefinitionError(
                    f"{label}: {cap_key} exceeds the maximum of {ceiling}"
                )


def _uploads_by_field(uploads: list | None) -> dict[str, list]:
    """Group ``OnboardingPacketUpload`` rows by ``field_id`` (None → empty)."""
    grouped: dict[str, list] = {}
    for upload in uploads or []:
        grouped.setdefault(upload.field_id, []).append(upload)
    return grouped


class UploadRequestDocumentType:
    """The file-collection document kind (gov-ID, designer assets, etc.)."""

    kind = "upload_request"
    needs_pdf_copy = False  # no template PDF to copy
    produces_signature = False
    records_view_via_stream = False  # records the view via POST /viewed

    def validate_definitions(
        self, defs: list[dict], *, pdf_bytes: bytes | None
    ) -> list[dict]:
        # ``pdf_bytes`` is deliberately ignored (P0-9): branch BEFORE any read.
        # The validated list is the canonical stored form (no model to normalize).
        validate_upload_definitions(defs)
        return defs

    def validate_value(
        self, field: dict, value: object
    ) -> tuple[object, bytes | None]:
        """Tolerant fill-time check for a file field's answer.

        Files are uploaded via the dedicated ``/files`` endpoint, which writes
        the upload-row id list into ``field_values[field_id]`` itself — so a
        PATCH should never carry a file field. Be tolerant per the contract:
        accept ``None`` (cleared) or a ``list[int]`` of upload-row ids; reject
        anything else as a 422 (never silently coerce). Never produces ciphertext
        (the upload kind has no sensitive TEXT field).
        """
        fid = field.get("id")
        if value is None:
            return None, None
        if isinstance(value, list) and all(
            isinstance(v, int) and not isinstance(v, bool) for v in value
        ):
            return value, None
        raise PacketValidationError(
            f"Field '{fid}' must be a list of uploaded-file ids"
        )

    def required_satisfied(
        self,
        field: dict,
        values: dict,
        uploads: list | None = None,
        secrets: dict | None = None,
    ) -> bool:
        """A required file field needs ≥1 uploaded file; optional is always met.

        Counts the ACTUAL ``onboarding_packet_uploads`` rows passed in for this
        document (loaded by completion Phase A), NOT the ``field_values`` id
        list — the rows are the source of truth this table owns (a stale id in
        the answer JSONB after a delete can't satisfy the gate).
        """
        if field.get("kind") != "file_upload":
            return True
        if not field.get("required"):
            return True
        grouped = _uploads_by_field(uploads)
        fid = str(field.get("id") or "")
        return len(grouped.get(fid, [])) >= 1

    async def produce_artifact(
        self,
        db: AsyncSession,
        *,
        doc: OnboardingPacketDocument,
        packet: OnboardingPacket,
        signature_png: bytes | None,
        dry_run: bool = False,
    ) -> bytes | None:
        """Render a brand-headed Platypus MANIFEST PDF of the uploaded files.

        Files are already attached at FILL time, so this is purely an index the
        contact sees as the document's single ``attachment_id`` artifact. Groups
        the ``onboarding_packet_uploads`` rows by field (filename + human size).
        Prepends the shared LinkCreative brand header (§B.3); ``dry_run`` skips
        the logo network fetch but still renders the body so a content/build
        error surfaces in Phase A. NEVER fails on a missing/odd logo (the header
        degrades to text). Returns the PDF bytes.
        """
        # Lazy imports — reportlab, the brand header and the models all reach
        # into the app graph; keep the module importable in any order.
        import io
        from xml.sax.saxutils import escape

        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import (
            ListFlowable,
            ListItem,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )
        from sqlalchemy import select

        from src.onboarding.models import OnboardingPacketUpload
        from src.onboarding.pdf_branding import brand_header_flowables

        uploads = list(
            (
                await db.execute(
                    select(OnboardingPacketUpload)
                    .where(OnboardingPacketUpload.packet_document_id == doc.id)
                    .order_by(OnboardingPacketUpload.id)
                )
            )
            .scalars()
            .all()
        )
        grouped = _uploads_by_field(uploads)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "OnbUploadTitle",
            parent=styles["Heading1"],
            fontSize=15,
            spaceAfter=6,
        )
        field_style = ParagraphStyle(
            "OnbUploadField",
            parent=styles["Heading2"],
            fontSize=12,
            spaceBefore=8,
            spaceAfter=2,
        )
        body_style = styles["BodyText"]

        flow: list = await brand_header_flowables(db, fetch_logo=not dry_run)
        flow.append(
            Paragraph(escape(doc.original_filename or "Uploaded files"), title_style)
        )
        flow.append(
            Paragraph(
                f"{len(uploads)} file(s) received.", body_style
            )
        )

        defs_by_id: dict[str, dict] = {
            str(f["id"]): f
            for f in (doc.field_definitions or [])
            if f.get("id")
        }
        if not uploads:
            flow.append(Spacer(1, 8))
            flow.append(Paragraph("No files were uploaded.", body_style))
        else:
            # Group by the field order in the definition, then any unknown ids.
            ordered_field_ids = [
                fid for fid in defs_by_id if grouped.get(fid)
            ] + [fid for fid in grouped if fid not in defs_by_id]
            for fid in ordered_field_ids:
                field = defs_by_id.get(fid, {})
                label = field.get("label") or fid
                flow.append(Paragraph(escape(str(label)), field_style))
                items: list = [
                    ListItem(
                        Paragraph(
                            f"{escape(u.original_filename)} "
                            f"({_human_size(u.byte_size)})",
                            body_style,
                        )
                    )
                    for u in grouped[fid]
                ]
                flow.append(ListFlowable(items, bulletType="bullet"))

        buf = io.BytesIO()
        SimpleDocTemplate(buf, pagesize=LETTER).build(flow)
        return buf.getvalue()

    async def scrub(
        self,
        db: AsyncSession,
        *,
        doc: OnboardingPacketDocument,
        purge: bool = False,
    ) -> None:
        """KEEP the uploaded files on COMPLETION; delete them only on PURGE.

        On a successful completion (``purge=False``) the uploaded files ARE the
        deliverable — gov-ID, brand assets — that Lorenzo accesses from the
        contact's Attachments (F1-CONFIRMED: keep gov-ID indefinitely, no v1
        purge sweep). Deleting them here would destroy the very thing the form
        collected, so completion is a NO-OP. On a non-delivery terminal
        (``purge=True`` — revoke/expire/abandon/purge_pii) the files are orphaned
        PII: delete every upload Attachment via the canonical
        ``AttachmentService.delete_attachment`` (removes the storage object AND
        the row across the disk/R2 branch — never hand-rolls ``storage.delete``),
        delete its fence row, and null the answer refs. Secret-row deletion is
        handled kind-agnostically by ``scrub_packet`` (also purge-only).
        """
        if not purge:
            return  # completion: the uploaded files are the deliverable — keep them

        # Lazy imports — the attachments service + models reach the app graph.
        from sqlalchemy import select

        from src.attachments.service import AttachmentService
        from src.onboarding.models import OnboardingPacketUpload

        uploads = list(
            (
                await db.execute(
                    select(OnboardingPacketUpload).where(
                        OnboardingPacketUpload.packet_document_id == doc.id
                    )
                )
            )
            .scalars()
            .all()
        )
        attachments = AttachmentService(db)
        for upload in uploads:
            if upload.attachment_id is not None:
                attachment = await attachments.get_attachment(upload.attachment_id)
                if attachment is not None:
                    await attachments.delete_attachment(attachment)
            await db.delete(upload)
        doc.field_values = {}


# Discovered + registered by the kinds package auto-loader (it reads this
# module-level ``HANDLER``). Deliberately NO import from ``src.onboarding.kinds``
# here so handler modules stay leaf and discovery is cycle-free.
HANDLER = UploadRequestDocumentType()

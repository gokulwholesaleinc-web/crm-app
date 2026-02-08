"""Attachment service layer for file upload, listing, download, and deletion."""

import os
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import UploadFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.attachments.models import Attachment

# Configurable via env var, default 10MB
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(10 * 1024 * 1024)))

ALLOWED_EXTENSIONS = {
    "pdf", "docx", "xlsx", "csv",
    "png", "jpg", "jpeg", "gif",
    "txt",
}

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"


def _get_extension(filename: str) -> str:
    """Extract lowercase file extension without the dot."""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


class AttachmentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upload_file(
        self,
        file: UploadFile,
        entity_type: str,
        entity_id: int,
        user_id: int,
    ) -> Attachment:
        """Upload a file and create an attachment record."""
        # Validate extension
        ext = _get_extension(file.filename or "")
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"File type '.{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        # Read file content
        content = await file.read()
        file_size = len(content)

        # Validate size
        if file_size > MAX_UPLOAD_SIZE:
            raise ValueError(
                f"File size {file_size} bytes exceeds maximum of {MAX_UPLOAD_SIZE} bytes"
            )

        # Generate unique filename to avoid collisions
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        entity_dir = UPLOAD_DIR / entity_type / str(entity_id)
        entity_dir.mkdir(parents=True, exist_ok=True)
        file_path = entity_dir / unique_name

        # Write file to disk
        file_path.write_bytes(content)

        # Create DB record
        attachment = Attachment(
            filename=unique_name,
            original_filename=file.filename or unique_name,
            file_path=str(file_path.relative_to(UPLOAD_DIR)),
            file_size=file_size,
            mime_type=file.content_type or "application/octet-stream",
            entity_type=entity_type,
            entity_id=entity_id,
            uploaded_by=user_id,
        )
        self.db.add(attachment)
        await self.db.flush()
        await self.db.refresh(attachment)
        return attachment

    async def list_attachments(
        self,
        entity_type: str,
        entity_id: int,
    ) -> Tuple[List[Attachment], int]:
        """List all attachments for an entity."""
        query = (
            select(Attachment)
            .where(Attachment.entity_type == entity_type)
            .where(Attachment.entity_id == entity_id)
            .order_by(Attachment.created_at.desc())
        )
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        count_query = (
            select(func.count())
            .select_from(Attachment)
            .where(Attachment.entity_type == entity_type)
            .where(Attachment.entity_id == entity_id)
        )
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        return items, total

    async def get_attachment(self, attachment_id: int) -> Optional[Attachment]:
        """Get a single attachment by ID."""
        result = await self.db.execute(
            select(Attachment).where(Attachment.id == attachment_id)
        )
        return result.scalar_one_or_none()

    async def delete_attachment(self, attachment: Attachment) -> None:
        """Delete attachment record and remove file from disk."""
        file_path = UPLOAD_DIR / attachment.file_path
        if file_path.exists():
            file_path.unlink()

        await self.db.delete(attachment)
        await self.db.flush()

    def get_file_path(self, attachment: Attachment) -> Path:
        """Get the absolute file path for downloading."""
        return UPLOAD_DIR / attachment.file_path

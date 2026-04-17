"""Attachment service layer for file upload, listing, download, and deletion."""

import os
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.attachments.models import Attachment
from src.attachments.object_storage import (
    delete_object,
    generate_object_key,
    get_download_url,
    is_object_storage_available,
    upload_file_bytes,
)

MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(10 * 1024 * 1024)))

ALLOWED_EXTENSIONS = {
    "pdf", "docx", "xlsx", "csv",
    "png", "jpg", "jpeg", "gif",
    "txt",
}

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"


def _use_object_storage() -> bool:
    return is_object_storage_available()


def _get_extension(filename: str) -> str:
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
        category: str | None = None,
    ) -> Attachment:
        ext = _get_extension(file.filename or "")
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"File type '.{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )

        content = await file.read()
        file_size = len(content)

        if file_size > MAX_UPLOAD_SIZE:
            raise ValueError(
                f"File size {file_size} bytes exceeds maximum of {MAX_UPLOAD_SIZE} bytes"
            )

        unique_name = f"{uuid.uuid4().hex}.{ext}"
        content_type = file.content_type or "application/octet-stream"

        if _use_object_storage():
            object_key = generate_object_key(entity_type, entity_id, ext)
            await upload_file_bytes(content, object_key, content_type)
            file_path = f"obj://{object_key}"
        else:
            entity_dir = UPLOAD_DIR / entity_type / str(entity_id)
            entity_dir.mkdir(parents=True, exist_ok=True)
            disk_path = entity_dir / unique_name
            disk_path.write_bytes(content)
            file_path = str(disk_path.relative_to(UPLOAD_DIR))

        attachment = Attachment(
            filename=unique_name,
            original_filename=file.filename or unique_name,
            file_path=file_path,
            file_size=file_size,
            mime_type=content_type,
            entity_type=entity_type,
            entity_id=entity_id,
            uploaded_by=user_id,
            category=category,
        )
        self.db.add(attachment)
        await self.db.flush()
        await self.db.refresh(attachment)
        return attachment

    async def list_attachments(
        self,
        entity_type: str,
        entity_id: int,
        category: str | None = None,
    ) -> tuple[list[Attachment], int]:
        query = (
            select(Attachment)
            .where(Attachment.entity_type == entity_type)
            .where(Attachment.entity_id == entity_id)
        )
        if category:
            query = query.where(Attachment.category == category)
        query = query.order_by(Attachment.created_at.desc())
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        count_query = (
            select(func.count())
            .select_from(Attachment)
            .where(Attachment.entity_type == entity_type)
            .where(Attachment.entity_id == entity_id)
        )
        if category:
            count_query = count_query.where(Attachment.category == category)
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        return items, total

    async def get_attachment(self, attachment_id: int) -> Attachment | None:
        result = await self.db.execute(
            select(Attachment).where(Attachment.id == attachment_id)
        )
        return result.scalar_one_or_none()

    async def delete_attachment(self, attachment: Attachment) -> None:
        if attachment.file_path.startswith("obj://"):
            object_key = attachment.file_path[6:]
            await delete_object(object_key)
        else:
            file_path = UPLOAD_DIR / attachment.file_path
            if file_path.exists():
                file_path.unlink()

        await self.db.delete(attachment)
        await self.db.flush()

    def get_file_path(self, attachment: Attachment) -> Path | None:
        if attachment.file_path.startswith("obj://"):
            return None
        return UPLOAD_DIR / attachment.file_path

    async def get_download_url(self, attachment: Attachment) -> str | None:
        if attachment.file_path.startswith("obj://"):
            object_key = attachment.file_path[6:]
            return await get_download_url(object_key)
        return None

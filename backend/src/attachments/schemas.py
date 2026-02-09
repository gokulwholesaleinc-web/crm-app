"""Pydantic schemas for attachments."""

from datetime import datetime
from typing import List
from pydantic import BaseModel, ConfigDict


class AttachmentResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    entity_type: str
    entity_id: int
    uploaded_by: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AttachmentListResponse(BaseModel):
    items: List[AttachmentResponse]
    total: int

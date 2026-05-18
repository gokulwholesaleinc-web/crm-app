from __future__ import annotations

import io
import os
import sys

import pytest
from fastapi import HTTPException, UploadFile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))

from src.auth.models import User
from src.import_export.router import (
    MAX_CSV_FILE_SIZE,
    _read_csv_upload,
    import_companies,
)

pytestmark = pytest.mark.asyncio


def _upload(content: bytes, *, filename: str = "contacts.csv", size: int | None = None):
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        size=len(content) if size is None else size,
    )


async def test_read_csv_upload_rejects_bad_encoding_as_400():
    with pytest.raises(HTTPException) as exc:
        await _read_csv_upload(_upload(b"name\n\xff\n"))

    assert exc.value.status_code == 400
    assert exc.value.detail == "CSV file must be UTF-8 encoded"


async def test_read_csv_upload_rejects_declared_oversize_before_read():
    upload = _upload(b"name\nok\n", size=MAX_CSV_FILE_SIZE + 1)

    with pytest.raises(HTTPException) as exc:
        await _read_csv_upload(upload)

    assert exc.value.status_code == 400
    assert exc.value.detail == "File size exceeds 10MB limit"
    assert upload.file.tell() == 0


async def test_import_companies_rejects_invalid_contact_decisions_json():
    current_user = User(
        id=1,
        email="admin@example.test",
        hashed_password="hash",
        full_name="Admin",
        is_active=True,
        is_approved=True,
        role="admin",
    )

    with pytest.raises(HTTPException) as exc:
        await import_companies(
            current_user=current_user,
            db=None,
            file=_upload(b"name\nAcme\n", filename="companies.csv"),
            contact_decisions="{not-json",
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "contact_decisions must be valid JSON"

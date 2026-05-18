from __future__ import annotations

import io
import os
import sys

import pytest
from fastapi import HTTPException, UploadFile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../"))

from src.proposals.router import _require_declared_pdf_size


def _upload(size: int | None) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(b"%PDF-1.4\n"),
        filename="contract.pdf",
        size=size,
    )


def test_require_declared_pdf_size_rejects_missing_size():
    with pytest.raises(HTTPException) as exc:
        _require_declared_pdf_size(
            _upload(None),
            missing_detail="master contract upload size is required",
            oversized_detail="master contract exceeds 25 MB limit",
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "master contract upload size is required"


def test_require_declared_pdf_size_rejects_oversize():
    with pytest.raises(HTTPException) as exc:
        _require_declared_pdf_size(
            _upload(25 * 1024 * 1024 + 1),
            missing_detail="signing document upload size is required",
            oversized_detail="signing document exceeds 25 MB limit",
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "signing document exceeds 25 MB limit"


def test_require_declared_pdf_size_allows_size_at_cap():
    _require_declared_pdf_size(
        _upload(25 * 1024 * 1024),
        missing_detail="master contract upload size is required",
        oversized_detail="master contract exceeds 25 MB limit",
    )

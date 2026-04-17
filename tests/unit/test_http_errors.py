"""Tests for src.core.http_errors.value_error_as_400."""

import pytest
from fastapi import HTTPException

from src.core.http_errors import value_error_as_400


def test_value_error_becomes_http_400_with_original_message():
    with pytest.raises(HTTPException) as exc_info:
        with value_error_as_400():
            raise ValueError("domain validation failed")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "domain validation failed"
    # Chain preserves the ValueError so FastAPI's error handler can log it.
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_non_value_error_propagates_unchanged():
    with pytest.raises(RuntimeError, match="unrelated"):
        with value_error_as_400():
            raise RuntimeError("unrelated")


def test_no_exception_is_a_noop():
    with value_error_as_400():
        result = 1 + 1
    assert result == 2

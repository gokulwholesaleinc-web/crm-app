"""Unit tests for core/router_utils.py — pure helpers, no async/db fixtures required."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.core.router_utils import (
    calculate_pages,
    check_ownership,
    effective_owner_id,
    parse_comma_separated,
    parse_json_filters,
    parse_tag_ids,
    raise_bad_request,
    raise_forbidden,
    raise_not_found,
)


class TestParseTagIds:
    def test_happy_path(self):
        assert parse_tag_ids("1,2,3") == [1, 2, 3]

    def test_none_returns_none(self):
        assert parse_tag_ids(None) is None

    def test_empty_string_returns_none(self):
        assert parse_tag_ids("") is None

    def test_whitespace_stripping(self):
        assert parse_tag_ids(" 1 , 2 , 3 ") == [1, 2, 3]

    def test_single_value(self):
        assert parse_tag_ids("42") == [42]

    def test_non_numeric_raises(self):
        with pytest.raises(ValueError):
            parse_tag_ids("1,abc,3")


class TestParseCommaSeparated:
    def test_happy_path(self):
        assert parse_comma_separated("email,call,meeting") == ["email", "call", "meeting"]

    def test_none_returns_none(self):
        assert parse_comma_separated(None) is None

    def test_empty_string_returns_none(self):
        assert parse_comma_separated("") is None

    def test_whitespace_stripping(self):
        assert parse_comma_separated(" email , call , meeting ") == ["email", "call", "meeting"]

    def test_single_value(self):
        assert parse_comma_separated("email") == ["email"]

    def test_trailing_comma_ignored(self):
        result = parse_comma_separated("email,call,")
        assert result == ["email", "call"]


class TestRaiseNotFound:
    def test_with_entity_id_raises_404(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("Contact", 99)
        assert exc_info.value.status_code == 404
        assert "Contact" in exc_info.value.detail
        assert "99" in exc_info.value.detail

    def test_without_entity_id_raises_404(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("Lead")
        assert exc_info.value.status_code == 404
        assert "Lead" in exc_info.value.detail

    def test_without_entity_id_detail_omits_id(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_not_found("Company")
        assert "ID" not in exc_info.value.detail


class TestRaiseBadRequest:
    def test_raises_400_with_message(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_bad_request("Invalid payload")
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid payload"


class TestRaiseForbidden:
    def test_raises_403_with_custom_message(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_forbidden("Access denied for this resource")
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Access denied for this resource"

    def test_raises_403_with_default_message(self):
        with pytest.raises(HTTPException) as exc_info:
            raise_forbidden()
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail  # non-empty default


class TestCheckOwnership:
    def _user(self, user_id, is_superuser=False, role="sales_rep"):
        return SimpleNamespace(id=user_id, is_superuser=is_superuser, role=role)

    def test_superuser_bypasses_check(self):
        entity = SimpleNamespace(owner_id=999)
        check_ownership(entity, self._user(1, is_superuser=True))

    def test_admin_role_bypasses_check(self):
        entity = SimpleNamespace(owner_id=999)
        check_ownership(entity, self._user(1, role="admin"))

    def test_manager_role_bypasses_check(self):
        entity = SimpleNamespace(owner_id=999)
        check_ownership(entity, self._user(1, role="manager"))

    def test_owner_can_modify(self):
        entity = SimpleNamespace(owner_id=42)
        check_ownership(entity, self._user(42))

    def test_non_owner_sales_rep_raises_403(self):
        entity = SimpleNamespace(owner_id=99)
        with pytest.raises(HTTPException) as exc_info:
            check_ownership(entity, self._user(42), entity_name="Contact")
        assert exc_info.value.status_code == 403
        assert "contact" in exc_info.value.detail.lower()


class TestCalculatePages:
    def test_exact_division(self):
        assert calculate_pages(100, 10) == 10

    def test_partial_last_page(self):
        assert calculate_pages(101, 10) == 11

    def test_single_item(self):
        assert calculate_pages(1, 20) == 1

    def test_zero_items(self):
        assert calculate_pages(0, 20) == 0


class TestParseJsonFilters:
    def test_valid_json(self):
        result = parse_json_filters('{"status": "active"}')
        assert result == {"status": "active"}

    def test_none_returns_none(self):
        assert parse_json_filters(None) is None

    def test_empty_string_returns_none(self):
        assert parse_json_filters("") is None

    def test_invalid_json_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_json_filters("{bad json}")
        assert exc_info.value.status_code == 400


class TestEffectiveOwnerId:
    def _scope(self, can_see_all: bool, owner_id: int):
        return SimpleNamespace(can_see_all=lambda: can_see_all, owner_id=owner_id)

    def test_can_see_all_returns_requested(self):
        scope = self._scope(can_see_all=True, owner_id=1)
        assert effective_owner_id(scope, requested_owner_id=99) == 99

    def test_restricted_returns_scope_owner(self):
        scope = self._scope(can_see_all=False, owner_id=5)
        assert effective_owner_id(scope, requested_owner_id=99) == 5

    def test_can_see_all_with_none_requested(self):
        scope = self._scope(can_see_all=True, owner_id=1)
        assert effective_owner_id(scope, requested_owner_id=None) is None

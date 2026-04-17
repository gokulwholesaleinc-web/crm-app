"""Unit tests for core/filtering.py — operators, group parsing, query application, token search."""

import pytest
from sqlalchemy import select
from sqlalchemy.sql import ClauseElement
from sqlalchemy.ext.asyncio import AsyncSession

from src.contacts.models import Contact
from src.core.filtering import (
    apply_filter_condition,
    apply_filters_to_query,
    build_token_search,
    parse_filter_group,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_clause(expr) -> bool:
    return isinstance(expr, ClauseElement)


def _make_contact(first_name: str, last_name: str, status: str = "active") -> Contact:
    return Contact(
        first_name=first_name,
        last_name=last_name,
        email=f"{first_name.lower()}.{last_name.lower()}@example.com",
        status=status,
        owner_id=1,
        created_by_id=1,
    )


# ---------------------------------------------------------------------------
# TestApplyFilterCondition — expression-level tests (no DB needed)
# ---------------------------------------------------------------------------

class TestApplyFilterCondition:
    """Tests for apply_filter_condition — all 12 operators."""

    def test_eq(self):
        expr = apply_filter_condition(Contact, "status", "eq", "active")
        assert _is_clause(expr)

    def test_neq(self):
        expr = apply_filter_condition(Contact, "status", "neq", "inactive")
        assert _is_clause(expr)

    def test_contains(self):
        expr = apply_filter_condition(Contact, "first_name", "contains", "john")
        assert _is_clause(expr)

    def test_not_contains(self):
        expr = apply_filter_condition(Contact, "first_name", "not_contains", "bot")
        assert _is_clause(expr)

    def test_gt(self):
        expr = apply_filter_condition(Contact, "id", "gt", 5)
        assert _is_clause(expr)

    def test_lt(self):
        expr = apply_filter_condition(Contact, "id", "lt", 100)
        assert _is_clause(expr)

    def test_gte(self):
        expr = apply_filter_condition(Contact, "id", "gte", 1)
        assert _is_clause(expr)

    def test_lte(self):
        expr = apply_filter_condition(Contact, "id", "lte", 999)
        assert _is_clause(expr)

    def test_in_with_list(self):
        assert _is_clause(apply_filter_condition(Contact, "status", "in", ["active", "inactive"]))

    def test_in_auto_wraps_scalar(self):
        assert _is_clause(apply_filter_condition(Contact, "status", "in", "active"))

    def test_not_in_with_list(self):
        assert _is_clause(apply_filter_condition(Contact, "status", "not_in", ["deleted"]))

    def test_not_in_auto_wraps_scalar(self):
        assert _is_clause(apply_filter_condition(Contact, "status", "not_in", "deleted"))

    def test_is_empty(self):
        assert _is_clause(apply_filter_condition(Contact, "email", "is_empty", None))

    def test_is_not_empty(self):
        assert _is_clause(apply_filter_condition(Contact, "email", "is_not_empty", None))

    def test_between_valid(self):
        assert _is_clause(apply_filter_condition(Contact, "id", "between", [1, 100]))

    def test_between_invalid_raises(self):
        with pytest.raises(ValueError, match="between"):
            apply_filter_condition(Contact, "id", "between", 42)

    def test_between_wrong_length_raises(self):
        with pytest.raises(ValueError, match="between"):
            apply_filter_condition(Contact, "id", "between", [1])

    def test_unknown_operator_raises(self):
        with pytest.raises(ValueError, match="Unknown operator"):
            apply_filter_condition(Contact, "status", "fuzzy", "active")

    def test_unknown_field_raises(self):
        with pytest.raises(ValueError, match="Unknown field"):
            apply_filter_condition(Contact, "nonexistent_col", "eq", "x")


# ---------------------------------------------------------------------------
# TestParseFilterGroup — structural tests
# ---------------------------------------------------------------------------

class TestParseFilterGroup:
    """Tests for parse_filter_group — single conditions, AND/OR, nested, empty."""

    def test_single_condition_field_key(self):
        """Dict with 'field' key delegates to apply_filter_condition."""
        expr = parse_filter_group(Contact, {"field": "status", "op": "eq", "value": "active"})
        assert _is_clause(expr)

    def test_and_group(self):
        """AND group with two conditions produces a compound clause."""
        expr = parse_filter_group(Contact, {
            "operator": "and",
            "conditions": [
                {"field": "status", "op": "eq", "value": "active"},
                {"field": "first_name", "op": "contains", "value": "john"},
            ],
        })
        assert _is_clause(expr)
        assert "AND" in str(expr).upper()

    def test_or_group(self):
        """OR group with two conditions produces an OR clause."""
        expr = parse_filter_group(Contact, {
            "operator": "or",
            "conditions": [
                {"field": "status", "op": "eq", "value": "active"},
                {"field": "status", "op": "eq", "value": "pending"},
            ],
        })
        assert _is_clause(expr)
        assert "OR" in str(expr).upper()

    def test_empty_conditions_returns_none(self):
        """Empty conditions list returns None."""
        result = parse_filter_group(Contact, {"operator": "and", "conditions": []})
        assert result is None

    def test_nested_or_inside_and(self):
        """Nested OR inside AND produces a compound clause containing both."""
        expr = parse_filter_group(Contact, {
            "operator": "and",
            "conditions": [
                {"field": "status", "op": "eq", "value": "active"},
                {
                    "operator": "or",
                    "conditions": [
                        {"field": "first_name", "op": "eq", "value": "John"},
                        {"field": "first_name", "op": "eq", "value": "Jane"},
                    ],
                },
            ],
        })
        assert _is_clause(expr)
        sql = str(expr).upper()
        assert "AND" in sql
        assert "OR" in sql


# ---------------------------------------------------------------------------
# TestApplyFiltersToQuery — identity and DB integration
# ---------------------------------------------------------------------------

class TestApplyFiltersToQuery:
    """Tests for apply_filters_to_query."""

    def test_none_filters_returns_query_unchanged(self):
        """filters=None leaves the query untouched."""
        q = select(Contact)
        result = apply_filters_to_query(q, Contact, None)
        assert result is q

    def test_empty_dict_returns_query_unchanged(self):
        """filters={} leaves the query untouched."""
        q = select(Contact)
        result = apply_filters_to_query(q, Contact, {})
        assert result is q

    def test_valid_filter_adds_where_clause(self):
        """A real filter condition mutates the query's whereclause."""
        q = select(Contact)
        filtered = apply_filters_to_query(
            q, Contact, {"field": "status", "op": "eq", "value": "active"}
        )
        assert filtered is not q
        assert filtered.whereclause is not None

    async def test_integration_eq_filter(self, db_session: AsyncSession, test_user):
        """Rows are correctly filtered using eq against the real SQLite session."""
        db_session.add(_make_contact("Alice", "A", "active"))
        db_session.add(_make_contact("Bob", "B", "inactive"))
        db_session.add(_make_contact("Carol", "C", "active"))
        await db_session.flush()

        q = select(Contact)
        q = apply_filters_to_query(q, Contact, {"field": "status", "op": "eq", "value": "active"})
        result = await db_session.execute(q)
        rows = result.scalars().all()
        assert all(r.status == "active" for r in rows)
        names = {r.first_name for r in rows}
        assert "Alice" in names
        assert "Carol" in names
        assert "Bob" not in names


# ---------------------------------------------------------------------------
# TestBuildTokenSearch — expression structure + DB integration
# ---------------------------------------------------------------------------

class TestBuildTokenSearch:
    """Tests for build_token_search."""

    def test_empty_string_returns_none(self):
        assert build_token_search("", Contact.first_name, Contact.last_name) is None

    def test_whitespace_only_returns_none(self):
        assert build_token_search("   ", Contact.first_name, Contact.last_name) is None

    def test_single_token_produces_clause(self):
        expr = build_token_search("john", Contact.first_name, Contact.last_name)
        assert _is_clause(expr)

    def test_two_tokens_produce_and_of_two_ors(self):
        """'john sm' → AND(OR(first ilike %john%, last ilike %john%), OR(first ilike %sm%, last ilike %sm%))."""
        expr = build_token_search("john sm", Contact.first_name, Contact.last_name)
        assert _is_clause(expr)
        sql = str(expr).upper()
        assert "AND" in sql
        assert sql.count("OR") >= 1

    async def test_integration_token_search(self, db_session: AsyncSession, test_user):
        """'john sm' matches only 'John Smith', not 'Jane Doe' or 'Alice'."""
        db_session.add(_make_contact("John", "Smith"))
        db_session.add(_make_contact("Jane", "Doe"))
        db_session.add(_make_contact("Alice", "Brown"))
        await db_session.flush()

        condition = build_token_search("john sm", Contact.first_name, Contact.last_name)
        result = await db_session.execute(select(Contact).where(condition))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].first_name == "John"
        assert rows[0].last_name == "Smith"

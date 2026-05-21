"""Generic filter parser that converts filter JSON to SQLAlchemy conditions.

Supports filter operators: eq, neq, contains, not_contains, gt, lt, gte, lte,
in, not_in, is_empty, is_not_empty, between.

Supports AND/OR filter groups:
{
    "operator": "and",
    "conditions": [
        {"field": "status", "op": "eq", "value": "new"},
        {
            "operator": "or",
            "conditions": [
                {"field": "score", "op": "gte", "value": 50},
                {"field": "industry", "op": "eq", "value": "Technology"}
            ]
        }
    ]
}
"""

from typing import Any

from sqlalchemy import String, and_, cast, or_


def apply_filter_condition(model: type, field_name: str, op: str, value: Any):
    """Build a single SQLAlchemy filter condition."""
    column = getattr(model, field_name, None)
    if column is None:
        raise ValueError(f"Unknown field: {field_name}")

    if op == "eq":
        return column == value
    elif op == "neq":
        return column != value
    elif op == "contains":
        return cast(column, String).ilike(f"%{value}%")
    elif op == "not_contains":
        return ~cast(column, String).ilike(f"%{value}%")
    elif op == "gt":
        return column > value
    elif op == "lt":
        return column < value
    elif op == "gte":
        return column >= value
    elif op == "lte":
        return column <= value
    elif op == "in":
        if not isinstance(value, list):
            value = [value]
        return column.in_(value)
    elif op == "not_in":
        if not isinstance(value, list):
            value = [value]
        return ~column.in_(value)
    elif op == "is_empty":
        return or_(column.is_(None), column == "")
    elif op == "is_not_empty":
        return and_(column.is_not(None), column != "")
    elif op == "between":
        if isinstance(value, list) and len(value) == 2:
            return and_(column >= value[0], column <= value[1])
        raise ValueError("between operator requires a list of [min, max]")
    else:
        raise ValueError(f"Unknown operator: {op}")


def _looks_like_legacy_filter_mapping(filter_def: dict[str, Any]) -> bool:
    """Detect the legacy {field: {op/operator, value}} shape via positive check.

    Returns True only when every value is a dict carrying an 'op' or 'operator'.
    A malformed new-style group missing 'conditions' fails this check and falls
    through to a clearer error rather than being parsed as a sea of "Unknown
    field" failures.
    """
    if not filter_def:
        return False
    return all(
        isinstance(v, dict) and ("op" in v or "operator" in v)
        for v in filter_def.values()
    )


def _parse_legacy_filter_mapping(model: type, filter_def: dict[str, Any]):
    """Parse older saved-filter JSON keyed by field name.

    Early saved filters were stored as:
    {"status": {"operator": "eq", "value": "active"}}

    The smart-list builder now emits explicit condition groups, but accepting
    this shape keeps existing saved lists functional when selected on list
    pages.
    """
    parsed = []
    for field_name, spec in filter_def.items():
        if not isinstance(spec, dict):
            raise ValueError(f"Legacy filter for field '{field_name}' must be an object")
        op = spec.get("op") or spec.get("operator")
        if not op:
            raise ValueError(f"Legacy filter for field '{field_name}' requires an operator")
        parsed.append(apply_filter_condition(model, field_name, op, spec.get("value")))

    if not parsed:
        return None
    return and_(*parsed)


def parse_filter_group(model: type, filter_def: dict[str, Any]):
    """Parse a filter group (AND/OR) recursively into SQLAlchemy conditions.

    Args:
        model: SQLAlchemy model class
        filter_def: Filter definition dict with either:
            - {"field": ..., "op": ..., "value": ...} for a single condition
            - {"operator": "and"/"or", "conditions": [...]} for a group
    """
    if not isinstance(filter_def, dict):
        raise ValueError("Filter definition must be an object")

    if "field" in filter_def:
        if "op" not in filter_def:
            raise ValueError("Filter condition requires an operator")
        return apply_filter_condition(
            model,
            filter_def["field"],
            filter_def["op"],
            filter_def.get("value"),
        )

    if _looks_like_legacy_filter_mapping(filter_def):
        return _parse_legacy_filter_mapping(model, filter_def)

    if "conditions" not in filter_def:
        raise ValueError(
            "Filter group must include a 'conditions' list (with optional 'operator' of 'and'/'or')"
        )

    operator = filter_def.get("operator", "and")
    if operator not in ("and", "or"):
        raise ValueError(f"Unknown filter group operator: {operator}")

    conditions = filter_def.get("conditions", [])
    if not isinstance(conditions, list):
        raise ValueError("Filter group conditions must be a list")

    if not conditions:
        return None

    parsed = []
    for cond in conditions:
        result = parse_filter_group(model, cond)
        if result is not None:
            parsed.append(result)

    if not parsed:
        return None

    if operator == "or":
        return or_(*parsed)
    return and_(*parsed)


def apply_filters_to_query(query, model: type, filters: dict[str, Any] | None):
    """Apply a filter definition to an existing SQLAlchemy query.

    Args:
        query: SQLAlchemy select query
        model: SQLAlchemy model class
        filters: Filter definition dict or None

    Returns:
        Modified query with filters applied
    """
    if not filters:
        return query

    condition = parse_filter_group(model, filters)
    if condition is not None:
        query = query.where(condition)
    return query


def build_token_search(search: str, *columns):
    """Build a token-based search condition for SQLAlchemy.

    Splits the search query into space-separated tokens and requires each
    token to match at least one of the given columns (via ilike). All tokens
    must match for a row to be included.

    Example: "john sm" matches any row where one column contains "john" AND
    one column contains "sm" (e.g. first_name="John", last_name="Smith").

    Args:
        search: The search query string (e.g. "john sm")
        *columns: SQLAlchemy model columns to search against

    Returns:
        SQLAlchemy AND condition, or None if search is empty/whitespace.
    """
    tokens = search.strip().split()
    if not tokens:
        return None

    token_conditions = []
    for token in tokens:
        pattern = f"%{token}%"
        column_matches = [col.ilike(pattern) for col in columns]
        token_conditions.append(or_(*column_matches))

    return and_(*token_conditions)

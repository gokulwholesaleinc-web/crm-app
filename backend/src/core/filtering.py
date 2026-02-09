"""Generic advanced filtering for SQLAlchemy models."""

from typing import Any, Optional
from sqlalchemy import and_, or_


def apply_filter_condition(model, field_name: str, op: str, value: Any):
    """Build a single SQLAlchemy filter condition.

    Returns None if the field doesn't exist or operator is unknown.
    """
    col = getattr(model, field_name, None)
    if col is None:
        return None

    ops = {
        "eq": lambda: col == value,
        "neq": lambda: col != value,
        "contains": lambda: col.ilike(f"%{value}%"),
        "not_contains": lambda: ~col.ilike(f"%{value}%"),
        "gt": lambda: col > value,
        "lt": lambda: col < value,
        "gte": lambda: col >= value,
        "lte": lambda: col <= value,
        "in": lambda: col.in_(value),
        "not_in": lambda: ~col.in_(value),
        "is_empty": lambda: or_(col.is_(None), col == ""),
        "is_not_empty": lambda: and_(col.isnot(None), col != ""),
        "between": lambda: col.between(value[0], value[1]) if isinstance(value, list) and len(value) == 2 else None,
    }

    builder = ops.get(op)
    if builder is None:
        return None
    return builder()


def parse_filter_group(model, filter_def: dict):
    """Recursively parse a filter group (AND/OR with nested conditions).

    Filter definition format:
    {
        "operator": "and" | "or",
        "conditions": [
            {"field": "status", "op": "eq", "value": "new"},
            {"operator": "or", "conditions": [...]},  # nested group
        ]
    }
    """
    conditions = filter_def.get("conditions", [])
    if not conditions:
        return None

    clauses = []
    for cond in conditions:
        if "operator" in cond or "conditions" in cond:
            nested = parse_filter_group(model, cond)
            if nested is not None:
                clauses.append(nested)
        else:
            clause = apply_filter_condition(
                model, cond["field"], cond["op"], cond.get("value")
            )
            if clause is not None:
                clauses.append(clause)

    if not clauses:
        return None

    group_op = filter_def.get("operator", "and")
    if group_op == "or":
        return or_(*clauses)
    return and_(*clauses)


def apply_filters_to_query(query, model, filters: dict):
    """Apply a filter definition dict to a SQLAlchemy select query."""
    clause = parse_filter_group(model, filters)
    if clause is not None:
        query = query.where(clause)
    return query

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

from typing import Any, Dict, List, Optional, Type
from sqlalchemy import and_, or_, String, cast


def apply_filter_condition(model: Type, field_name: str, op: str, value: Any):
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
        return or_(column == None, column == "")
    elif op == "is_not_empty":
        return and_(column != None, column != "")
    elif op == "between":
        if isinstance(value, list) and len(value) == 2:
            return and_(column >= value[0], column <= value[1])
        raise ValueError("between operator requires a list of [min, max]")
    else:
        raise ValueError(f"Unknown operator: {op}")


def parse_filter_group(model: Type, filter_def: Dict[str, Any]):
    """Parse a filter group (AND/OR) recursively into SQLAlchemy conditions.

    Args:
        model: SQLAlchemy model class
        filter_def: Filter definition dict with either:
            - {"field": ..., "op": ..., "value": ...} for a single condition
            - {"operator": "and"/"or", "conditions": [...]} for a group
    """
    if "field" in filter_def:
        return apply_filter_condition(
            model,
            filter_def["field"],
            filter_def["op"],
            filter_def.get("value"),
        )

    operator = filter_def.get("operator", "and")
    conditions = filter_def.get("conditions", [])

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


def apply_filters_to_query(query, model: Type, filters: Optional[Dict[str, Any]]):
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

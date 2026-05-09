"""Allowlist-driven ORDER BY builder for list endpoints.

User-controlled `order_by` strings must never reach SQLAlchemy raw — that
would be a SQL-injection / DoS vector. Each entity passes a literal map of
URL keys to ORM column attributes; anything not in the map silently falls
back to the caller's default ordering.

Allowlist values may be a single column attribute or a tuple of attributes
(used when the user-facing `name` key needs to sort on `(last_name,
first_name)` because `full_name` is a Python property, not a column).
"""

from typing import Any


def build_order_clauses(
    sortable: dict[str, Any],
    order_by: str | None,
    order_dir: str | None,
    default: list[Any] | tuple[Any, ...],
) -> list[Any]:
    """Translate `(order_by, order_dir)` into a SQLAlchemy order_by tuple.

    - Unknown `order_by` => returns `default` unchanged.
    - `order_dir` not in {'asc', 'desc'} => coerced to 'desc'.
    - The caller's `default` clauses are appended after the user's chosen
      column as a stable tiebreaker so paginated lists with ties keep a
      deterministic order across pages.
    """
    if not order_by or order_by not in sortable:
        return list(default)

    direction = order_dir if order_dir in ("asc", "desc") else "desc"
    chosen = sortable[order_by]
    columns = list(chosen) if isinstance(chosen, list | tuple) else [chosen]

    primary = [c.asc() if direction == "asc" else c.desc() for c in columns]
    return primary + list(default)

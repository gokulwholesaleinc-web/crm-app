"""Shared ordered-set rewrite for onboarding join tables (audit B6 + V3-1/4).

A two-pass ``display_order`` rewrite that avoids the transient
``UNIQUE(parent, display_order)`` collision a naive per-row UPDATE trips: bump
every row to a temporary offset (PK-based, so the temp values are themselves
unique and out of the final range), flush, then write the final ``0..N-1``.

Generic over the row type via a ``pk`` getter and a ``set_order`` setter so both
``selection_service`` (proposal→template selections) and the bundle service
reuse the exact same rewrite instead of each open-coding it.

The CALLER owns the half that makes it concurrency-safe and correct: the
permutation check, the parent-row ``SELECT ... FOR UPDATE`` lock (which
serializes two writers so they can't race the unique constraint into a raw 500),
and ``updated_by_id`` stamping. This module only sequences the writes + flushes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

# A temporary offset larger than any realistic row count, so the first pass
# can't collide with a row's eventual final order.
_TEMP_ORDER_OFFSET = 1_000_000


def _default_pk(row: Any) -> int:
    return row.id


async def reorder_by_display_order(
    rows: Sequence[Any],
    ordered_ids: list[int],
    *,
    set_order: Callable[[Any, int], None],
    flush: Callable[[], Awaitable[None]],
    pk: Callable[[Any], int] = _default_pk,
) -> None:
    """Rewrite ``display_order`` to match ``ordered_ids`` with no transient
    unique collision.

    ``rows`` are the current rows in any order; ``ordered_ids`` is the desired
    order as a permutation of ``pk(row)`` (the caller validates the permutation).
    ``set_order(row, n)`` assigns the order field; ``flush`` is the session flush
    coroutine — the inter-pass flush is what clears the unique constraint before
    the final contiguous values land.
    """
    by_id = {pk(r): r for r in rows}
    # Pass 1: move every row out of the final range (PK-based temp → unique).
    for r in rows:
        set_order(r, _TEMP_ORDER_OFFSET + pk(r))
    await flush()
    # Pass 2: write the final contiguous 0..N-1 order.
    for order, rid in enumerate(ordered_ids):
        set_order(by_id[rid], order)
    await flush()

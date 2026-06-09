"""Search Console ingest — webmasters v3 searchAnalytics:query + pure mapper.

REST against ``sites/{siteUrl}/searchAnalytics/query`` with ``startRow`` paging
(≤25k rows/request per D3). The fetcher pages until a short page and lands the
concatenated rows under a stable ``{"rows": [...]}`` shape; ``map_gsc`` is PURE
over that payload.

GSC has no native sampling flag; metrics are clicks/impressions/ctr/position at a
``date`` grain (``dimension_type='total'`` here — GSC's per-date row IS the total
for the day at the site level). Empty payload → ``[]`` (E5 guard).
"""

from __future__ import annotations

from datetime import date as date_cls
from typing import Any

from ..money import q6
from ..rows import AnalyticsDailyRow
from .http_client import GSC_BASE, GoogleSeam, ensure_shape

_PAGE_SIZE = 25000  # D3 max rows/request


async def fetch_gsc(
    client: GoogleSeam,
    *,
    site_url: str,
    window_start: date_cls,
    window_end: date_cls,
    max_pages: int = 8,
) -> dict[str, Any]:
    """Fetch date-grain search analytics, paging on ``startRow`` (D3).

    ``site_url`` is the canonical property (``sc-domain:…`` or a URL-prefix; A10
    normalized on the connection). Bounded by ``max_pages`` so a runaway property
    can't blow the daily quota budget in one connection.
    """
    from urllib.parse import quote

    url = f"{GSC_BASE}/sites/{quote(site_url, safe='')}/searchAnalytics/query"
    all_rows: list[dict] = []
    start_row = 0
    for _ in range(max_pages):
        body = {
            "startDate": window_start.isoformat(),
            "endDate": window_end.isoformat(),
            "dimensions": ["date"],
            "rowLimit": _PAGE_SIZE,
            "startRow": start_row,
        }
        page = await client.post(url, body)
        rows = page.get("rows") or []
        all_rows.extend(rows)
        if len(rows) < _PAGE_SIZE:
            break
        start_row += _PAGE_SIZE
    return {"rows": all_rows}


def map_gsc(
    payload: dict[str, Any],
    *,
    connection_id: int,
    company_id: int,
) -> list[AnalyticsDailyRow]:
    """Pure: searchAnalytics payload → date-grain ``AnalyticsDailyRow``s.

    The ``keys`` array holds the requested dimensions in order — here just
    ``[date]``. clicks/impressions are ints; ctr/position are ``Decimal``. Empty
    payload → ``[]`` (E5 guard).
    """
    # Envelope guard (CRITICAL-1): the fetcher always lands {"rows": [...]} (empty
    # list when the site had no search traffic). A payload without the 'rows' key is
    # an error body / drifted shape — raise so the run is 'partial', not a silent
    # zero. A row missing its date key is likewise a shape drift, not empty data.
    ensure_shape(
        isinstance(payload, dict) and isinstance(payload.get("rows"), list),
        "gsc payload missing 'rows' list envelope",
        platform="gsc",
    )

    rows: list[AnalyticsDailyRow] = []
    for raw in payload["rows"]:
        keys = raw.get("keys") or []
        ensure_shape(
            bool(keys),
            "gsc row missing 'keys' (date dimension)",
            platform="gsc",
        )
        row_date = date_cls.fromisoformat(keys[0])
        rows.append(
            AnalyticsDailyRow(
                connection_id=connection_id,
                company_id=company_id,
                source="gsc",
                date=row_date,
                dimension_type="total",
                dimension_value="",
                clicks=int(raw.get("clicks", 0) or 0),
                impressions=int(raw.get("impressions", 0) or 0),
                ctr=q6(raw.get("ctr", 0) or 0),
                position=q6(raw.get("position", 0) or 0),
            )
        )
    return rows

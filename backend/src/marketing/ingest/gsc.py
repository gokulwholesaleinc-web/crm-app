"""Search Console ingest — webmasters v3 searchAnalytics:query + pure mapper.

REST against ``sites/{siteUrl}/searchAnalytics/query`` with ``startRow`` paging
(≤25k rows/request per D3). The fetcher pages until a short page and lands the
concatenated rows under a stable ``{"rows": [...]}`` shape; ``map_gsc`` is PURE
over that payload.

Three dimension shapes are pulled (each its own request → its own landing row):
* ``['date']`` → ``dimension_type='total'`` (GSC's per-date row IS the site-level
  total for the day; the read layer's totals come ONLY from these, A11);
* ``['date','query']`` → ``dimension_type='query'`` (top queries panel);
* ``['date','page']`` → ``dimension_type='page'`` (top pages panel).

The query/page shapes keep the **per-date** grain (Phase 3) so the daily rolling
re-fetch restates each day's rows idempotently (A2/A7) — the read layer sums over
the window. GSC has no native sampling flag; metrics are clicks/impressions/ctr/
position. Empty payload → ``[]`` (E5 guard).
"""

from __future__ import annotations

from datetime import date as date_cls
from typing import Any

from ..money import q6
from ..rows import AnalyticsDailyRow
from .http_client import GSC_BASE, GoogleSeam, ensure_shape

_PAGE_SIZE = 25000  # D3 max rows/request
# analytics_daily.dimension_value is String(512); a GSC page URL can exceed that,
# so the mapper truncates to keep a long URL from failing the whole run's insert.
_MAX_DIM_LEN = 512


async def fetch_gsc(
    client: GoogleSeam,
    *,
    site_url: str,
    window_start: date_cls,
    window_end: date_cls,
    dimensions: tuple[str, ...] = ("date",),
    max_pages: int = 8,
) -> dict[str, Any]:
    """Fetch search analytics for one ``dimensions`` shape, paging on ``startRow`` (D3).

    ``site_url`` is the canonical property (``sc-domain:…`` or a URL-prefix; A10
    normalized on the connection). ``dimensions`` defaults to ``('date',)`` (the
    total shape); pass ``('date','query')`` / ``('date','page')`` for the
    breakdown shapes. Bounded by ``max_pages`` so a runaway property can't blow the
    daily quota budget in one connection.
    """
    from urllib.parse import quote

    url = f"{GSC_BASE}/sites/{quote(site_url, safe='')}/searchAnalytics/query"
    all_rows: list[dict] = []
    start_row = 0
    for _ in range(max_pages):
        body = {
            "startDate": window_start.isoformat(),
            "endDate": window_end.isoformat(),
            "dimensions": list(dimensions),
            "rowLimit": _PAGE_SIZE,
            "startRow": start_row,
        }
        page = await client.post(url, body)
        # Drift guard at the fetch boundary (CRITICAL-1): a genuinely-empty result is
        # a dict with no/empty 'rows'; a 2xx ERROR-shaped body would otherwise be
        # normalized to {"rows": []} and recorded as a silent zero. (GSC's empty and
        # no-data shapes both lack 'rows', so only an explicit error envelope / a
        # non-dict is treated as drift.)
        if start_row == 0:
            # GSC has no single positive key (a genuine no-data day legitimately omits
            # 'rows'), so require a RECOGNIZABLE success shape: an empty dict {} or a
            # dict carrying 'rows' or 'responseAggregationType' (GSC returns the latter
            # on every successful query). An explicit 'error', or a non-empty dict with
            # none of those (a renamed/alien envelope, e.g. rows→entries), is drift →
            # raise rather than normalize to a silent zero (CRITICAL-1).
            ensure_shape(
                isinstance(page, dict)
                and "error" not in page
                and (len(page) == 0 or "rows" in page or "responseAggregationType" in page),
                "gsc searchAnalytics: unrecognized response envelope",
                platform="gsc",
            )
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
    dimension_type: str = "total",
) -> list[AnalyticsDailyRow]:
    """Pure: searchAnalytics payload → per-date ``AnalyticsDailyRow``s.

    The ``keys`` array holds the requested dimensions in order: ``[date]`` for the
    ``'total'`` shape, ``[date, query]`` / ``[date, page]`` for the breakdown
    shapes. ``dimension_value`` is ``""`` for totals, else the second key
    (truncated to the column width). clicks/impressions are ints; ctr/position are
    ``Decimal``. Empty payload → ``[]`` (E5 guard).
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
        if dimension_type == "total":
            dimension_value = ""
        else:
            # The breakdown shapes carry [date, <query|page>]; a row missing the
            # second key is a drifted shape, not empty data → raise (CRITICAL-1).
            ensure_shape(
                len(keys) >= 2,
                f"gsc {dimension_type} row missing its dimension key",
                platform="gsc",
            )
            dimension_value = (keys[1] or "")[:_MAX_DIM_LEN]
        rows.append(
            AnalyticsDailyRow(
                connection_id=connection_id,
                company_id=company_id,
                source="gsc",
                date=row_date,
                dimension_type=dimension_type,
                dimension_value=dimension_value,
                clicks=int(raw.get("clicks", 0) or 0),
                impressions=int(raw.get("impressions", 0) or 0),
                ctr=q6(raw.get("ctr", 0) or 0),
                position=q6(raw.get("position", 0) or 0),
            )
        )
    return rows

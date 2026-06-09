"""PageSpeed Insights ingest — v5 runPagespeed (API key) + pure mapper.

A GET against ``pagespeedonline/v5/runPagespeed`` per (url, strategy). No OAuth —
just the server-side API key on the client. ``map_pagespeed`` is PURE over one
Lighthouse result payload, emitting a single ``SiteHealthRow`` snapshot.

Scores are Lighthouse 0..1 → stored 0..100 (``Numeric(5,2)``). LCP/INP come from
audit ``numericValue`` (ms); CLS is unitless. Missing categories/audits → ``None``
(snapshots are sparse by design). A payload with no ``lighthouseResult`` → ``[]``
(E5 guard — never raise on a degraded response).
"""

from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal
from typing import Any

from ..money import q6
from ..rows import SiteHealthRow
from .http_client import PageSpeedSeam

_SCORE_KEYS = {
    "performance_score": "performance",
    "seo_score": "seo",
    "accessibility_score": "accessibility",
    "best_practices_score": "best-practices",
}


async def fetch_pagespeed(
    client: PageSpeedSeam, *, url: str, strategy: str
) -> dict[str, Any]:
    """Run PageSpeed for one (url, strategy); request the three scored categories."""
    return await client.run(
        {
            "url": url,
            "strategy": strategy,
            # repeated category params — httpx encodes a list as repeated keys
            "category": ["performance", "accessibility", "seo", "best-practices"],
        }
    )


def _score(categories: dict[str, Any], key: str) -> Decimal | None:
    cat = categories.get(key)
    if not cat:
        return None
    raw = cat.get("score")
    if raw is None:
        return None
    return q6(Decimal(str(raw)) * 100)  # Lighthouse 0..1 → 0..100


def _audit_ms(audits: dict[str, Any], audit_id: str) -> int | None:
    audit = audits.get(audit_id)
    if not audit:
        return None
    raw = audit.get("numericValue")
    return int(round(float(raw))) if raw is not None else None


def _cls(audits: dict[str, Any]) -> Decimal | None:
    audit = audits.get("cumulative-layout-shift")
    if not audit:
        return None
    raw = audit.get("numericValue")
    return q6(raw) if raw is not None else None


def map_pagespeed(
    payload: dict[str, Any],
    *,
    connection_id: int,
    company_id: int,
    captured_date: date_cls,
    strategy: str,
) -> list[SiteHealthRow]:
    """Pure: a Lighthouse result → one ``SiteHealthRow`` snapshot.

    Returns a list (0 or 1 rows) so the orchestrator treats every mapper the same
    way. A response missing ``lighthouseResult`` yields ``[]`` (E5 guard).
    """
    lh = payload.get("lighthouseResult")
    if not lh:
        return []

    categories = lh.get("categories", {})
    audits = lh.get("audits", {})
    final_url = lh.get("finalUrl") or lh.get("requestedUrl") or payload.get("id", "")

    return [
        SiteHealthRow(
            connection_id=connection_id,
            company_id=company_id,
            captured_date=captured_date,
            strategy=strategy,
            url=final_url,
            performance_score=_score(categories, _SCORE_KEYS["performance_score"]),
            seo_score=_score(categories, _SCORE_KEYS["seo_score"]),
            accessibility_score=_score(categories, _SCORE_KEYS["accessibility_score"]),
            best_practices_score=_score(categories, _SCORE_KEYS["best_practices_score"]),
            lcp_ms=_audit_ms(audits, "largest-contentful-paint"),
            cls=_cls(audits),
            inp_ms=_audit_ms(audits, "interaction-to-next-paint"),
        )
    ]

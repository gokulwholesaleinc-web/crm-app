"""Canonical ``external_account_id`` normalization (A10).

Each platform identifies an account differently and admins paste them in varied
forms ("123-456-7890", "act_123", "properties/447532899"). Normalizing on write
means the ``uq_platform_connections_identity`` unique can't admit the same
account twice under two spellings (``act_123`` vs ``123``).
"""

from __future__ import annotations

import re

_NON_DIGITS = re.compile(r"\D")


def normalize_external_account_id(platform: str, raw: str) -> str:
    """Return the canonical id for ``platform`` (A10). Unknown platforms pass
    through trimmed."""
    value = (raw or "").strip()
    if platform == "google_ads":
        # 10-digit customer id, dashes/spaces stripped.
        return _NON_DIGITS.sub("", value)
    if platform == "ga4":
        # bare numeric property id ("properties/447532899" -> "447532899").
        return value.split("/")[-1].strip()
    if platform == "meta_ads":
        # always "act_<digits>".
        digits = value[4:] if value.startswith("act_") else value
        digits = _NON_DIGITS.sub("", digits)
        return f"act_{digits}" if digits else value
    # gsc (sc-domain:/URL-prefix), pagespeed (URL), social (page/org ids):
    # keep verbatim — only trimmed.
    return value


def normalize_manager_account_id(manager_account_id: str | None) -> str | None:
    """MCC / login-customer-id → digits only (Google Ads); ``None`` passes through."""
    if not manager_account_id:
        return None
    return _NON_DIGITS.sub("", manager_account_id) or None

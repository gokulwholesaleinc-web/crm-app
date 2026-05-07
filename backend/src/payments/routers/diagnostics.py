"""Stripe diagnostics sub-router."""

import logging

from fastapi import APIRouter

from src.config import settings
from src.core.router_utils import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()


def _publishable_prefix(pk: str | None) -> str | None:
    """Return just the env-prefix (`pk_test_` / `pk_live_`) of a publishable
    key, never the full value. Field is a hint for the UI's banner copy —
    no caller needs the full key, and trimming avoids the response shape
    suggesting otherwise."""
    if not pk:
        return None
    for prefix in ("pk_test_", "pk_live_"):
        if pk.startswith(prefix):
            return prefix
    return None


# Stripe accepts both standard secret keys (`sk_*`) and restricted keys
# (`rk_*`) for API calls. Restricted keys are scoped to a subset of
# resources — recommended for production deployments where the platform
# only needs (say) Customers + Invoices + Subscriptions, not full
# account access. `_get_stripe()` already accepts either; this endpoint
# previously only recognised `sk_*`, so a working `rk_*`-keyed install
# kept reporting "unconfigured" and the SendInvoiceModal showed a stale
# warning banner.
_LIVE_PREFIXES = ("sk_live_", "rk_live_")
_TEST_PREFIXES = ("sk_test_", "rk_test_")


@router.get("/mode")
async def get_stripe_mode(current_user: CurrentUser) -> dict:
    """Return Stripe key mode: live, test, or unconfigured."""
    key = settings.STRIPE_SECRET_KEY or ""

    if any(key.startswith(p) for p in _LIVE_PREFIXES):
        mode = "live"
    elif any(key.startswith(p) for p in _TEST_PREFIXES):
        mode = "test"
    else:
        mode = "unconfigured"

    # Temporary diagnostic to isolate a "Stripe is not configured" banner
    # report on prod where the env var is set to a working `rk_test_…`
    # key. Logs only the prefix length + first 8 chars of the prefix
    # (never the secret material) plus the resolved mode. Remove once
    # the report is closed.
    key_present = bool(key)
    prefix = key[:8] if key else "(empty)"
    logger.info(
        "[stripe-mode-diag] key_present=%s prefix=%s mode=%s",
        key_present,
        prefix,
        mode,
    )

    return {
        "mode": mode,
        "publishable_hint": _publishable_prefix(getattr(settings, "STRIPE_PUBLISHABLE_KEY", None)),
    }

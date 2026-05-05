"""Stripe diagnostics sub-router."""

from fastapi import APIRouter

from src.config import settings
from src.core.router_utils import CurrentUser

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


@router.get("/mode")
async def get_stripe_mode(current_user: CurrentUser) -> dict:
    """Return Stripe key mode: live, test, or unconfigured."""
    key = settings.STRIPE_SECRET_KEY or ""

    if key.startswith("sk_live_"):
        mode = "live"
    elif key.startswith("sk_test_"):
        mode = "test"
    else:
        mode = "unconfigured"

    return {
        "mode": mode,
        "publishable_hint": _publishable_prefix(getattr(settings, "STRIPE_PUBLISHABLE_KEY", None)),
    }

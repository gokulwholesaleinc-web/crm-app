"""Stripe diagnostics sub-router."""

from fastapi import APIRouter

from src.config import settings
from src.core.router_utils import CurrentUser

router = APIRouter()


@router.get("/mode")
async def get_stripe_mode(current_user: CurrentUser) -> dict:
    """Return Stripe key mode: live, test, or unconfigured."""
    key = settings.STRIPE_SECRET_KEY or ""

    if not key:
        mode = "unconfigured"
        hint = None
    elif key.startswith("sk_live_"):
        mode = "live"
        hint = settings.STRIPE_PUBLISHABLE_KEY or None
    elif key.startswith("sk_test_"):
        mode = "test"
        hint = settings.STRIPE_PUBLISHABLE_KEY or None
    else:
        mode = "unconfigured"
        hint = None

    return {"mode": mode, "publishable_hint": hint}

"""Settings API routes - provides /api/settings/* namespace."""

from fastapi import APIRouter

from src.core.router_utils import DBSession, CurrentUser
from src.email.schemas import EmailSettingsResponse, EmailSettingsUpdate
from src.email.throttle import EmailThrottleService

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/email", response_model=EmailSettingsResponse)
async def get_email_settings(
    current_user: CurrentUser,
    db: DBSession,
):
    """Get email settings (daily limits, warmup config)."""
    throttle = EmailThrottleService(db)
    settings = await throttle.get_settings()
    return EmailSettingsResponse.model_validate(settings)


@router.put("/email", response_model=EmailSettingsResponse)
async def update_email_settings(
    data: EmailSettingsUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update email settings (daily limits, warmup config)."""
    from datetime import date as date_type
    warmup_date = None
    if data.warmup_start_date:
        warmup_date = date_type.fromisoformat(data.warmup_start_date)

    throttle = EmailThrottleService(db)
    settings = await throttle.update_settings(
        daily_send_limit=data.daily_send_limit,
        warmup_enabled=data.warmup_enabled,
        warmup_start_date=warmup_date,
        warmup_target_daily=data.warmup_target_daily,
    )
    return EmailSettingsResponse.model_validate(settings)

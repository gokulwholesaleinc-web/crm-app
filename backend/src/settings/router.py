"""Settings API routes - provides /api/settings/* namespace."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from src.auth.dependencies import get_current_superuser
from src.core.permissions import require_manager_or_above
from src.core.router_utils import DBSession
from src.email.schemas import EmailSettingsResponse, EmailSettingsUpdate
from src.email.throttle import EmailThrottleService

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Email settings are a global singleton row and a DoS surface (a low daily
# limit blocks every outbound email), so reads are manager-or-above and
# writes are superuser-only.
ManagerOrAbove = Annotated[Any, Depends(require_manager_or_above)]
SuperUser = Annotated[Any, Depends(get_current_superuser)]


@router.get("/email", response_model=EmailSettingsResponse)
async def get_email_settings(
    current_user: ManagerOrAbove,
    db: DBSession,
):
    """Get email settings (daily limits, warmup config). Manager+ only."""
    throttle = EmailThrottleService(db)
    settings = await throttle.get_settings()
    return EmailSettingsResponse.model_validate(settings)


@router.put("/email", response_model=EmailSettingsResponse)
async def update_email_settings(
    data: EmailSettingsUpdate,
    current_user: SuperUser,
    db: DBSession,
):
    """Update email settings (daily limits, warmup config). Superuser only."""
    throttle = EmailThrottleService(db)
    settings = await throttle.update_settings(
        daily_send_limit=data.daily_send_limit,
        warmup_enabled=data.warmup_enabled,
        warmup_start_date=data.parsed_warmup_date,
        warmup_target_daily=data.warmup_target_daily,
    )
    return EmailSettingsResponse.model_validate(settings)

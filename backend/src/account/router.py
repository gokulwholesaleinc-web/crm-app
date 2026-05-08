"""Account-settings endpoints (per-user notification + display prefs)."""

from fastapi import APIRouter

from src.account.schemas import (
    AccountPreferencesResponse,
    AccountPreferencesUpdate,
    NotificationPrefsResponse,
    NotificationPrefsUpdate,
)
from src.account.service import AccountPrefsService
from src.core.router_utils import CurrentUser, DBSession

router = APIRouter(prefix="/api/account", tags=["account"])


@router.get("/notifications", response_model=NotificationPrefsResponse)
async def get_notification_prefs(current_user: CurrentUser, db: DBSession):
    service = AccountPrefsService(db)
    return await service.get_or_create_notification_prefs(current_user.id)


@router.put("/notifications", response_model=NotificationPrefsResponse)
async def update_notification_prefs(
    payload: NotificationPrefsUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    service = AccountPrefsService(db)
    return await service.update_notification_prefs(current_user.id, payload)


@router.get("/preferences", response_model=AccountPreferencesResponse)
async def get_preferences(current_user: CurrentUser, db: DBSession):
    service = AccountPrefsService(db)
    return await service.get_or_create_preferences(current_user.id)


@router.put("/preferences", response_model=AccountPreferencesResponse)
async def update_preferences(
    payload: AccountPreferencesUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    service = AccountPrefsService(db)
    return await service.update_preferences(current_user.id, payload)

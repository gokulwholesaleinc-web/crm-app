"""Admin API — composed from domain sub-routers."""
from fastapi import APIRouter

from src.admin.routers import approval, audit, observability, users

router = APIRouter(prefix="/api/admin", tags=["admin"])
router.include_router(approval.router)
router.include_router(audit.router)
router.include_router(users.router)
router.include_router(observability.router)

"""Contract aggregate stats endpoint."""

from datetime import date, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from src.contracts.models import Contract
from src.core.router_utils import CurrentUser, DBSession

router = APIRouter(prefix="/api/contracts", tags=["contracts"])


class ContractStatusBreakdown(BaseModel):
    draft: int = 0
    sent: int = 0
    signed: int = 0
    active: int = 0
    expired: int = 0
    terminated: int = 0


class ContractStats(BaseModel):
    total_active_value: float
    expiring_this_month: int
    status_breakdown: ContractStatusBreakdown


@router.get("/stats", response_model=ContractStats)
async def get_contract_stats(
    _current_user: CurrentUser,
    db: DBSession,
) -> ContractStats:
    """Aggregate contract metrics for the Reports dashboard."""
    today = date.today()
    in_30_days = today + timedelta(days=30)

    # Active value sum
    value_result = await db.execute(
        select(func.coalesce(func.sum(Contract.value), 0.0)).where(
            Contract.status == "active"
        )
    )
    total_active_value: float = float(value_result.scalar() or 0.0)

    # Count expiring this month (active contracts whose end_date is within 30 days)
    expiring_result = await db.execute(
        select(func.count()).where(
            Contract.status == "active",
            Contract.end_date.isnot(None),
            Contract.end_date >= today,
            Contract.end_date <= in_30_days,
        )
    )
    expiring_this_month: int = expiring_result.scalar() or 0

    # Status breakdown
    breakdown_result = await db.execute(
        select(Contract.status, func.count().label("cnt"))
        .group_by(Contract.status)
    )
    rows = breakdown_result.all()
    counts: dict[str, int] = {row.status: row.cnt for row in rows}

    return ContractStats(
        total_active_value=total_active_value,
        expiring_this_month=expiring_this_month,
        status_breakdown=ContractStatusBreakdown(
            draft=counts.get("draft", 0),
            sent=counts.get("sent", 0),
            signed=counts.get("signed", 0),
            active=counts.get("active", 0),
            expired=counts.get("expired", 0),
            terminated=counts.get("terminated", 0),
        ),
    )

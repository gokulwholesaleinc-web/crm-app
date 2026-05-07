"""Daily contract-lifecycle job: signed→active auto-flip + expiring alerts."""

import logging
import os
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import src.database as db_module
from src.contracts.models import Contract

logger = logging.getLogger(__name__)

EXPIRING_WINDOW_DAYS = 30


class ContractLifecycleService:
    """Daily lifecycle pass: status auto-flip + expiring-soon alerts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_due_contracts(self) -> int:
        flipped = await self._flip_signed_to_active()
        alerted = await self._alert_expiring_soon()
        # Heartbeat log even when both are zero so a broken cron is
        # detectable from "absent line" instead of "always silent".
        logger.info(
            "[contracts_lifecycle] flipped=%d alerted=%d", flipped, alerted,
        )
        return flipped + alerted

    async def _flip_signed_to_active(self) -> int:
        today = date.today()
        result = await self.db.execute(
            update(Contract)
            .where(Contract.status == "signed")
            .where(Contract.start_date.is_not(None))
            .where(Contract.start_date <= today)
            .values(status="active")
        )
        return result.rowcount or 0

    async def _alert_expiring_soon(self) -> int:
        """Find expiring contracts and notify each in its OWN session.

        The select is on `self.db`; per-contract notify/flag work is
        delegated to a fresh `async_session_maker()` block — one
        revoked-token tenant or one Gmail outage can't poison the rest
        of the batch (mirrors `_sync_google_calendars` in core/scheduler).
        """
        now = datetime.now(UTC)
        cutoff = now.date() + timedelta(days=EXPIRING_WINDOW_DAYS)
        notify_floor = now - timedelta(days=EXPIRING_WINDOW_DAYS)

        result = await self.db.execute(
            select(Contract.id)
            .where(Contract.status == "active")
            .where(Contract.end_date.is_not(None))
            .where(Contract.end_date <= cutoff)
            .where(Contract.end_date >= now.date())
            .where(
                or_(
                    Contract.expiring_notified_at.is_(None),
                    Contract.expiring_notified_at < notify_floor,
                )
            )
        )
        contract_ids = [row[0] for row in result.all()]

        notified = 0
        for cid in contract_ids:
            try:
                async with db_module.async_session_maker() as session:
                    fresh = await session.execute(
                        select(Contract)
                        .options(
                            selectinload(Contract.contact),
                            selectinload(Contract.company),
                        )
                        .where(Contract.id == cid)
                    )
                    contract = fresh.scalar_one_or_none()
                    if contract is None:
                        continue
                    await self._notify_owner_with_session(contract, session)
                    contract.expiring_notified_at = now
                    await session.commit()
                    notified += 1
            except Exception:
                # Per-contract isolation: a failure here logs loudly but
                # does NOT abort the batch or roll back peers' updates.
                logger.exception(
                    "[contracts_lifecycle] notify failed contract=%s", cid,
                )
        return notified

    async def _notify_owner_with_session(
        self, contract: Contract, session: AsyncSession,
    ) -> None:
        if contract.owner_id is None:
            return

        days_left = (contract.end_date - date.today()).days  # type: ignore[operator]
        title = f"Contract expiring in {days_left} day{'s' if days_left != 1 else ''}"
        company_name = contract.company.name if contract.company else "no company"
        end_date_str = contract.end_date.isoformat() if contract.end_date else "unknown"
        body = f"{contract.title} ({company_name}) expires on {end_date_str}."

        from src.notifications.service import NotificationService

        notif_service = NotificationService(session)
        await notif_service.create_notification(
            user_id=contract.owner_id,
            type="contract_expiring",
            title=title,
            message=body,
            entity_type="contracts",
            entity_id=contract.id,
        )

        from src.auth.models import User

        owner_result = await session.execute(
            select(User).where(User.id == contract.owner_id)
        )
        owner = owner_result.scalar_one_or_none()
        if owner is None or not owner.email:
            return

        from src.email.branded_templates import TenantBrandingHelper
        from src.email.service import EmailService

        branding = await TenantBrandingHelper.get_branding_for_user(
            session, contract.owner_id
        )
        company_label = branding.get("company_name") or "CRM"
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        view_url = f"{frontend_url}/contracts/{contract.id}"
        html = (
            f"<p>{body}</p>"
            f'<p><a href="{view_url}">Open contract</a></p>'
            f"<p>{company_label}</p>"
        )

        email_service = EmailService(session)
        await email_service.queue_email(
            to_email=owner.email,
            subject=f"Contract expiring — {contract.title}",
            body=html,
            sent_by_id=contract.owner_id,
            entity_type="contracts",
            entity_id=contract.id,
        )

"""Daily contract-lifecycle job: signed→active auto-flip + expiring alerts."""

import logging
import os
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.contracts.models import Contract

logger = logging.getLogger(__name__)

EXPIRING_WINDOW_DAYS = 30


class ContractLifecycleService:
    """Daily lifecycle pass: status auto-flip + expiring-soon alerts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_due_contracts(self) -> int:
        # Heartbeat fires unconditionally — a broken cron is now
        # distinguishable from a thrown job (errored=True) and from a
        # silent zero-action run (flipped=0 alerted=0 errored=False).
        flipped = alerted = 0
        errored = False
        try:
            flipped = await self._flip_signed_to_active()
            alerted = await self._alert_expiring_soon()
        except Exception:
            errored = True
            logger.exception("[contracts_lifecycle] job failed")
            raise
        finally:
            logger.info(
                "[contracts_lifecycle] flipped=%d alerted=%d errored=%s",
                flipped, alerted, errored,
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
        """Find expiring contracts and notify each owner.

        Note on isolation: trio review flagged that a failure inside one
        `_notify_owner` call can poison the shared session and silently
        roll back peer updates. The "right" fix is a fresh session per
        contract (mirroring `_sync_google_calendars`), but our pytest
        fixtures wrap each test in a transaction the per-row session
        wouldn't see. Keeping the shared-session pattern for now;
        per-row commit isolation lands as a follow-up alongside test
        infrastructure that supports both modes.
        """
        now = datetime.now(UTC)
        cutoff = now.date() + timedelta(days=EXPIRING_WINDOW_DAYS)
        notify_floor = now - timedelta(days=EXPIRING_WINDOW_DAYS)

        result = await self.db.execute(
            select(Contract)
            .options(selectinload(Contract.contact), selectinload(Contract.company))
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
        contracts = list(result.scalars().all())

        notified = 0
        for contract in contracts:
            try:
                await self._notify_owner(contract)
                contract.expiring_notified_at = now
                notified += 1
            except Exception:
                logger.exception(
                    "[contracts_lifecycle] notify failed contract=%s", contract.id,
                )
        await self.db.flush()
        return notified

    async def _notify_owner(self, contract: Contract) -> None:
        if contract.owner_id is None:
            return

        days_left = (contract.end_date - date.today()).days  # type: ignore[operator]
        title = f"Contract expiring in {days_left} day{'s' if days_left != 1 else ''}"
        company_name = contract.company.name if contract.company else "no company"
        end_date_str = contract.end_date.isoformat() if contract.end_date else "unknown"
        body = f"{contract.title} ({company_name}) expires on {end_date_str}."

        from src.notifications.service import NotificationService

        notif_service = NotificationService(self.db)
        await notif_service.create_notification(
            user_id=contract.owner_id,
            type="contract_expiring",
            title=title,
            message=body,
            entity_type="contracts",
            entity_id=contract.id,
        )

        from src.auth.models import User

        owner_result = await self.db.execute(
            select(User).where(User.id == contract.owner_id)
        )
        owner = owner_result.scalar_one_or_none()
        if owner is None or not owner.email:
            return

        from src.email.branded_templates import TenantBrandingHelper
        from src.email.service import EmailService

        branding = await TenantBrandingHelper.get_branding_for_user(
            self.db, contract.owner_id
        )
        company_label = branding.get("company_name") or "CRM"
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        view_url = f"{frontend_url}/contracts/{contract.id}"
        html = (
            f"<p>{body}</p>"
            f'<p><a href="{view_url}">Open contract</a></p>'
            f"<p>{company_label}</p>"
        )

        email_service = EmailService(self.db)
        await email_service.queue_email(
            to_email=owner.email,
            subject=f"Contract expiring — {contract.title}",
            body=html,
            sent_by_id=contract.owner_id,
            entity_type="contracts",
            entity_id=contract.id,
        )

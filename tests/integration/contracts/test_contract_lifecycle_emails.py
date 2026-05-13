"""Integration tests for contract lifecycle email + notification dispatching.

All tests use the real SQLite in-memory DB (no mocks) via conftest fixtures.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Send paths gate on assert_gmail_connected (PR #310).
pytestmark = pytest.mark.usefixtures("gmail_connected_test_user")

from src.account.models import UserNotificationPrefs
from src.auth.models import User
from src.companies.models import Company
from src.contacts.models import Contact
from src.contracts.models import Contract
from src.contracts.scheduler import ContractLifecycleService
from src.contracts.service import ContractService
from src.email.models import EmailQueue
from src.notifications.models import Notification

DUMMY_SIG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


async def _active_contract_expiring_soon(
    db: AsyncSession, owner: User, company: Company | None = None, days: int = 14
) -> Contract:
    c = Contract(
        title="Expiry Test Contract",
        scope="scope",
        status="active",
        end_date=date.today() + timedelta(days=days),
        owner_id=owner.id,
        company_id=company.id if company else None,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def _sent_contract(
    db: AsyncSession,
    owner: User,
    contact: Contact | None = None,
) -> Contract:
    """Create a contract, send it for signature, and return it."""
    c = Contract(
        title="Sign Test Contract",
        scope="scope",
        status="draft",
        owner_id=owner.id,
        contact_id=contact.id if contact else None,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)

    svc = ContractService(db)
    to_email = contact.email if contact else "signer@example.com"
    return await svc.send_for_signature(c, user_id=owner.id, to_email=to_email if not contact else None)


class TestContractExpiringEmailSent:
    """Expiring scheduler queues a branded email when email is allowed."""

    async def test_email_queued_with_branded_subject(
        self,
        db_session: AsyncSession,
        test_user_opted_in: User,
        test_company: Company,
    ):
        test_user = test_user_opted_in
        contract = await _active_contract_expiring_soon(db_session, test_user, test_company)
        await ContractLifecycleService(db_session).process_due_contracts()

        result = await db_session.execute(
            select(EmailQueue).where(EmailQueue.entity_type == "contracts").where(EmailQueue.entity_id == contract.id)
        )
        rows = list(result.scalars().all())
        assert len(rows) == 1
        row = rows[0]
        assert row.to_email == test_user.email
        assert "expiring" in row.subject.lower()
        assert contract.title in row.body


class TestContractExpiringEmailSuppressed:
    """Expiring scheduler skips email when contract_expiring is disabled; in-app still fires."""

    async def test_no_email_queued_when_opt_out(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_company: Company,
    ):
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            in_app_enabled=True,
            email_enabled=True,
            event_matrix={"contract_expiring": {"in_app": True, "email": False}},
        )
        db_session.add(prefs)
        await db_session.commit()

        contract = await _active_contract_expiring_soon(db_session, test_user, test_company)
        await ContractLifecycleService(db_session).process_due_contracts()

        result = await db_session.execute(
            select(EmailQueue).where(EmailQueue.entity_type == "contracts").where(EmailQueue.entity_id == contract.id)
        )
        rows = list(result.scalars().all())
        assert len(rows) == 0

        # In-app notification should still be written
        notif_result = await db_session.execute(
            select(Notification).where(Notification.entity_id == contract.id).where(Notification.type == "contract_expiring")
        )
        assert notif_result.scalar_one_or_none() is not None


class TestContractSignedBothEmailsQueued:
    """After sign_contract: signer gets transactional email, owner gets notification email."""

    async def test_signer_and_owner_emails_queued(
        self,
        db_session: AsyncSession,
        test_user_opted_in: User,
        test_contact: Contact,
    ):
        test_user = test_user_opted_in
        contract = await _sent_contract(db_session, test_user, test_contact)
        svc = ContractService(db_session)

        await svc.sign_contract(
            contract,
            signer_name="Jane Signer",
            signer_email=test_contact.email,
            signature_data_url=DUMMY_SIG,
        )

        result = await db_session.execute(
            select(EmailQueue).where(EmailQueue.entity_type == "contracts").where(EmailQueue.entity_id == contract.id)
        )
        rows = list(result.scalars().all())

        # Filter to only the post-sign emails (send_for_signature also queues one)
        signer_rows = [r for r in rows if r.to_email == test_contact.email and "Signed copy" in r.subject]
        owner_rows = [r for r in rows if r.to_email == test_user.email and "signed" in r.subject.lower()]

        assert len(signer_rows) == 1, f"Expected 1 signer email, got {len(signer_rows)}"
        assert len(owner_rows) == 1, f"Expected 1 owner email, got {len(owner_rows)}"

        assert contract.title in signer_rows[0].subject
        assert contract.title in owner_rows[0].subject


class TestContractSignedOwnerEmailSuppressed:
    """With contract_signed email disabled, signer still gets email but owner does not."""

    async def test_signer_email_always_on_owner_suppressed(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        prefs = UserNotificationPrefs(
            user_id=test_user.id,
            event_matrix={"contract_signed": {"email": False}},
        )
        db_session.add(prefs)
        await db_session.commit()

        contract = await _sent_contract(db_session, test_user, test_contact)
        svc = ContractService(db_session)

        await svc.sign_contract(
            contract,
            signer_name="Jane Signer",
            signer_email=test_contact.email,
            signature_data_url=DUMMY_SIG,
        )

        result = await db_session.execute(
            select(EmailQueue).where(EmailQueue.entity_type == "contracts").where(EmailQueue.entity_id == contract.id)
        )
        rows = list(result.scalars().all())

        signer_rows = [r for r in rows if r.to_email == test_contact.email and "Signed copy" in r.subject]
        owner_email_rows = [r for r in rows if r.to_email == test_user.email and "signed" in r.subject.lower()]

        assert len(signer_rows) == 1, "Signer transactional email must still fire"
        assert len(owner_email_rows) == 0, "Owner email must be suppressed by matrix"


class TestContractSignedNotificationWritten:
    """NotificationService writes a contract_signed row for the owner after signing."""

    async def test_notification_row_created(
        self,
        db_session: AsyncSession,
        test_user_opted_in: User,
        test_contact: Contact,
    ):
        test_user = test_user_opted_in
        contract = await _sent_contract(db_session, test_user, test_contact)
        svc = ContractService(db_session)

        await svc.sign_contract(
            contract,
            signer_name="Jane Signer",
            signer_email=test_contact.email,
            signature_data_url=DUMMY_SIG,
        )

        result = await db_session.execute(
            select(Notification)
            .where(Notification.user_id == test_user.id)
            .where(Notification.type == "contract_signed")
            .where(Notification.entity_id == contract.id)
        )
        notif = result.scalar_one_or_none()
        assert notif is not None, "Expected a contract_signed Notification row for the owner"

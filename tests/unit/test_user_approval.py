"""Unit tests for user approval gate, reject list, and admin approval endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User, RejectedAccessEmail
from src.auth.security import create_access_token, get_password_hash
from src.notifications.models import Notification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin_headers(admin: User) -> dict:
    token = create_access_token(data={"sub": str(admin.id)})
    return {"Authorization": f"Bearer {token}"}


def _user_headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# /register endpoint removed
# ---------------------------------------------------------------------------

class TestRegisterRemoved:
    @pytest.mark.asyncio
    async def test_register_returns_404(self, client: AsyncClient):
        """POST /api/auth/register must return 404 now that the endpoint is removed."""
        response = await client.post(
            "/api/auth/register",
            json={"email": "new@example.com", "password": "pass", "full_name": "New"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Google OAuth approval gate (via service layer)
# ---------------------------------------------------------------------------

class TestGoogleOAuthApprovalGate:
    @pytest.mark.asyncio
    async def test_new_google_user_gets_is_approved_false(
        self, db_session: AsyncSession
    ):
        """A brand-new Google sign-in sets is_approved=False."""
        from src.auth.service import AuthService

        service = AuthService(db_session)
        user = await service.upsert_google_user(
            google_sub="google-sub-new-001",
            email="brandnew@example.com",
            full_name="Brand New",
        )
        await db_session.commit()

        assert user.is_approved is False
        assert user.email == "brandnew@example.com"

    @pytest.mark.asyncio
    async def test_existing_user_keeps_is_approved(self, db_session: AsyncSession):
        """An already-approved user signing in again stays approved."""
        from src.auth.service import AuthService

        existing = User(
            email="existing@example.com",
            hashed_password=get_password_hash("pass"),
            full_name="Existing",
            is_active=True,
            is_approved=True,
        )
        db_session.add(existing)
        await db_session.commit()
        await db_session.refresh(existing)

        service = AuthService(db_session)
        user = await service.upsert_google_user(
            google_sub="google-sub-existing",
            email="existing@example.com",
            full_name="Existing",
        )
        assert user.is_approved is True

    @pytest.mark.asyncio
    async def test_rejected_email_raises_error(self, db_session: AsyncSession):
        """An email on the reject list raises RejectedAccessError."""
        from src.auth.service import AuthService, RejectedAccessError

        rejected = RejectedAccessEmail(
            email="blocked@example.com",
            rejected_by_id=None,
        )
        db_session.add(rejected)
        await db_session.commit()

        service = AuthService(db_session)
        with pytest.raises(RejectedAccessError):
            await service.upsert_google_user(
                google_sub="google-sub-blocked",
                email="Blocked@example.com",  # mixed-case to test lowercasing
                full_name="Blocked User",
            )

        # No user row should have been created
        result = await db_session.execute(
            select(User).where(User.email == "Blocked@example.com")
        )
        assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Admin notification on pending sign-up
# ---------------------------------------------------------------------------

class TestAdminNotificationOnPendingSignup:
    @pytest.mark.asyncio
    async def test_admin_receives_notification_for_pending_user(
        self, db_session: AsyncSession
    ):
        """Each admin gets a notification when a new pending user signs up."""
        from src.notifications.service import notify_admins_of_pending_user

        admin1 = User(
            email="adminnotif1@example.com",
            hashed_password=get_password_hash("pass"),
            full_name="Admin One",
            is_active=True,
            is_superuser=True,
        )
        admin2 = User(
            email="adminnotif2@example.com",
            hashed_password=get_password_hash("pass"),
            full_name="Admin Two",
            is_active=True,
            is_superuser=False,
            role="admin",
        )
        pending = User(
            email="pending@example.com",
            hashed_password=None,
            full_name="Pending User",
            is_active=True,
            is_approved=False,
        )
        db_session.add_all([admin1, admin2, pending])
        await db_session.commit()
        await db_session.refresh(admin1)
        await db_session.refresh(admin2)
        await db_session.refresh(pending)

        await notify_admins_of_pending_user(db_session, pending)
        await db_session.flush()

        notifs = (await db_session.execute(
            select(Notification).where(Notification.type == "pending_approval")
        )).scalars().all()

        notified_ids = {n.user_id for n in notifs}
        assert admin1.id in notified_ids
        assert admin2.id in notified_ids
        assert len(notifs) == 2


# ---------------------------------------------------------------------------
# Admin approval endpoints
# ---------------------------------------------------------------------------

class TestAdminApprovalEndpoints:
    @pytest.fixture
    def admin_user(self, test_superuser: User) -> User:
        return test_superuser

    @pytest.fixture
    def admin_hdrs(self, admin_user: User) -> dict:
        return _admin_headers(admin_user)

    @pytest.fixture
    def sales_rep_hdrs(self, test_user: User) -> dict:
        return _user_headers(test_user)

    @pytest.mark.asyncio
    async def test_list_pending_users_as_admin(
        self, client: AsyncClient, db_session: AsyncSession, admin_hdrs: dict
    ):
        """Admin can list pending users."""
        pending = User(
            email="pending2@example.com",
            hashed_password=None,
            full_name="Pending Two",
            is_active=True,
            is_approved=False,
        )
        db_session.add(pending)
        await db_session.commit()

        response = await client.get("/api/admin/users/pending", headers=admin_hdrs)
        assert response.status_code == 200
        emails = [u["email"] for u in response.json()]
        assert "pending2@example.com" in emails

    @pytest.mark.asyncio
    async def test_list_pending_users_forbidden_for_sales_rep(
        self, client: AsyncClient, sales_rep_hdrs: dict
    ):
        """Sales rep cannot access pending users list."""
        response = await client.get("/api/admin/users/pending", headers=sales_rep_hdrs)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_approve_user_sets_approved_and_role(
        self, client: AsyncClient, db_session: AsyncSession, admin_hdrs: dict
    ):
        """Approving a pending user sets is_approved=True and assigns role."""
        pending = User(
            email="approve_me@example.com",
            hashed_password=None,
            full_name="Approve Me",
            is_active=True,
            is_approved=False,
        )
        db_session.add(pending)
        await db_session.commit()
        await db_session.refresh(pending)

        response = await client.patch(
            f"/api/admin/users/{pending.id}/approve",
            json={"role": "sales_rep"},
            headers=admin_hdrs,
        )
        assert response.status_code == 204

        await db_session.refresh(pending)
        assert pending.is_approved is True
        assert pending.role == "sales_rep"

    @pytest.mark.asyncio
    async def test_approve_already_approved_returns_400(
        self, client: AsyncClient, db_session: AsyncSession, admin_hdrs: dict, test_user: User
    ):
        """Re-approving an already-approved user returns 400."""
        response = await client.patch(
            f"/api/admin/users/{test_user.id}/approve",
            json={"role": "sales_rep"},
            headers=admin_hdrs,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_approve_endpoint_forbidden_for_sales_rep(
        self, client: AsyncClient, db_session: AsyncSession, sales_rep_hdrs: dict, test_user: User
    ):
        """Non-admin cannot approve users."""
        response = await client.patch(
            f"/api/admin/users/{test_user.id}/approve",
            json={"role": "sales_rep"},
            headers=sales_rep_hdrs,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_reject_user_creates_block_entry_and_deletes_user(
        self, client: AsyncClient, db_session: AsyncSession,
        admin_hdrs: dict, admin_user: User
    ):
        """Rejecting a user inserts a rejected_access_emails row and hard-deletes the user."""
        target = User(
            email="Reject_Me@example.com",
            hashed_password=None,
            full_name="Reject Me",
            is_active=True,
            is_approved=False,
        )
        db_session.add(target)
        await db_session.commit()
        await db_session.refresh(target)
        target_id = target.id

        response = await client.post(
            f"/api/admin/users/{target_id}/reject",
            json={"reason": "spam account"},
            headers=admin_hdrs,
        )
        assert response.status_code == 200
        data = response.json()
        assert "rejected_email_id" in data

        # User row must be gone
        result = await db_session.execute(select(User).where(User.id == target_id))
        assert result.scalar_one_or_none() is None

        # Rejected email stored lowercased
        result = await db_session.execute(
            select(RejectedAccessEmail).where(RejectedAccessEmail.email == "reject_me@example.com")
        )
        entry = result.scalar_one_or_none()
        assert entry is not None
        assert entry.reason == "spam account"
        assert entry.rejected_by_id == admin_user.id

    @pytest.mark.asyncio
    async def test_reject_endpoint_forbidden_for_sales_rep(
        self, client: AsyncClient, db_session: AsyncSession,
        sales_rep_hdrs: dict, test_user: User
    ):
        """Non-admin cannot reject users."""
        response = await client.post(
            f"/api/admin/users/{test_user.id}/reject",
            json={},
            headers=sales_rep_hdrs,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_rejected_emails(
        self, client: AsyncClient, db_session: AsyncSession, admin_hdrs: dict
    ):
        """Admin can list all rejected emails."""
        entry = RejectedAccessEmail(
            email="listed_blocked@example.com",
            rejected_by_id=None,
        )
        db_session.add(entry)
        await db_session.commit()

        response = await client.get("/api/admin/rejected-emails", headers=admin_hdrs)
        assert response.status_code == 200
        emails = [r["email"] for r in response.json()]
        assert "listed_blocked@example.com" in emails

    @pytest.mark.asyncio
    async def test_delete_rejected_email_removes_block(
        self, client: AsyncClient, db_session: AsyncSession, admin_hdrs: dict
    ):
        """Deleting a rejected email entry removes the block."""
        entry = RejectedAccessEmail(
            email="unblock_me@example.com",
            rejected_by_id=None,
        )
        db_session.add(entry)
        await db_session.commit()
        await db_session.refresh(entry)

        response = await client.delete(
            f"/api/admin/rejected-emails/{entry.id}",
            headers=admin_hdrs,
        )
        assert response.status_code == 204

        result = await db_session.execute(
            select(RejectedAccessEmail).where(RejectedAccessEmail.id == entry.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_list_rejected_emails_forbidden_for_sales_rep(
        self, client: AsyncClient, sales_rep_hdrs: dict
    ):
        """Non-admin cannot list rejected emails."""
        response = await client.get("/api/admin/rejected-emails", headers=sales_rep_hdrs)
        assert response.status_code == 403

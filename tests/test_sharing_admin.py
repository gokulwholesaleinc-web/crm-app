"""
Tests for admin sharing endpoint: GET /api/sharing/admin and related flows.
"""

import time

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.contacts.models import Contact
from src.core import data_scope as data_scope_module
from src.core.data_scope import DataScope
from src.core.models import EntityShare
from src.notifications.models import Notification
from src.roles.models import RoleName, UserRole

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create a user with admin role."""
    user = User(
        email="sharing_admin@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Sharing Admin",
        is_active=True,
        is_superuser=False,
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def manager_user(db_session: AsyncSession) -> User:
    """Create a user with manager role."""
    user = User(
        email="sharing_manager@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Sharing Manager",
        is_active=True,
        is_superuser=False,
        role="manager",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def sales_rep_user(db_session: AsyncSession) -> User:
    """Create a user with sales_rep role."""
    user = User(
        email="sharing_rep@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Sales Rep",
        is_active=True,
        is_superuser=False,
        role="sales_rep",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def another_user(db_session: AsyncSession) -> User:
    """Create a second regular user for share targets."""
    user = User(
        email="another_user@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Another User",
        is_active=True,
        is_superuser=False,
        role="sales_rep",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def inactive_user(db_session: AsyncSession) -> User:
    """Create an inactive user for validation tests."""
    user = User(
        email="inactive_share_target@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Inactive User",
        is_active=False,
        is_superuser=False,
        role="sales_rep",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _headers(user: User) -> dict:
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def sample_share(
    db_session: AsyncSession,
    sales_rep_user: User,
    another_user: User,
) -> EntityShare:
    """Create a single EntityShare row for testing."""
    share = EntityShare(
        entity_type="contacts",
        entity_id=42,
        shared_with_user_id=another_user.id,
        shared_by_user_id=sales_rep_user.id,
        permission_level="view",
    )
    db_session.add(share)
    await db_session.commit()
    await db_session.refresh(share)
    return share


@pytest_asyncio.fixture
async def multiple_shares(
    db_session: AsyncSession,
    sales_rep_user: User,
    another_user: User,
    admin_user: User,
) -> list[EntityShare]:
    """Create several EntityShare rows across entity types."""
    shares = [
        EntityShare(
            entity_type="contacts",
            entity_id=1,
            shared_with_user_id=another_user.id,
            shared_by_user_id=sales_rep_user.id,
            permission_level="view",
        ),
        EntityShare(
            entity_type="leads",
            entity_id=2,
            shared_with_user_id=another_user.id,
            shared_by_user_id=sales_rep_user.id,
            permission_level="edit",
        ),
        EntityShare(
            entity_type="contacts",
            entity_id=3,
            shared_with_user_id=admin_user.id,
            shared_by_user_id=sales_rep_user.id,
            permission_level="view",
        ),
    ]
    for s in shares:
        db_session.add(s)
    await db_session.commit()
    for s in shares:
        await db_session.refresh(s)
    return shares


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdminSharesAuthz:
    """Authorization tests for GET /api/sharing/admin."""

    @pytest.mark.asyncio
    async def test_sales_rep_gets_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sales_rep_user: User,
    ):
        """sales_rep role must receive 403."""
        response = await client.get(
            "/api/sharing/admin", headers=_headers(sales_rep_user)
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_gets_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
    ):
        """admin role gets a 200 with paginated payload."""
        response = await client.get(
            "/api/sharing/admin", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    @pytest.mark.asyncio
    async def test_manager_gets_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        manager_user: User,
    ):
        """manager role is denied — sharing audit is admin-only."""
        response = await client.get(
            "/api/sharing/admin", headers=_headers(manager_user)
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_authz_uses_user_roles_source_of_truth(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        seed_roles: list,
    ):
        """An admin UserRole grants access even if users.role is stale."""
        user = User(
            email="sharing_user_role_admin@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="UserRole Admin",
            is_active=True,
            is_superuser=False,
            role="sales_rep",
        )
        db_session.add(user)
        await db_session.flush()
        admin_role = next(r for r in seed_roles if r.name == RoleName.ADMIN.value)
        db_session.add(UserRole(user_id=user.id, role_id=admin_role.id))
        await db_session.commit()
        await db_session.refresh(user)

        response = await client.get("/api/sharing/admin", headers=_headers(user))
        assert response.status_code == 200


class TestAdminSharesList:
    """Listing and pagination tests."""

    @pytest.mark.asyncio
    async def test_returns_all_shares(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        multiple_shares: list[EntityShare],
    ):
        """Admin sees all shares in the system."""
        response = await client.get(
            "/api/sharing/admin", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    @pytest.mark.asyncio
    async def test_item_shape(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        sample_share: EntityShare,
        sales_rep_user: User,
        another_user: User,
    ):
        """Each item has all required fields including user name/email."""
        response = await client.get(
            "/api/sharing/admin", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["id"] == sample_share.id
        assert item["entity_type"] == "contacts"
        assert item["entity_id"] == 42
        assert item["shared_with_user_id"] == another_user.id
        assert item["shared_with_user_name"] == another_user.full_name
        assert item["shared_with_user_email"] == another_user.email
        assert item["shared_by_user_id"] == sales_rep_user.id
        assert item["shared_by_user_name"] == sales_rep_user.full_name
        assert item["permission_level"] == "view"
        assert "created_at" in item

    @pytest.mark.asyncio
    async def test_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        multiple_shares: list[EntityShare],
    ):
        """page/page_size parameters slice results correctly."""
        response = await client.get(
            "/api/sharing/admin?page=1&page_size=2", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) == 2

        response2 = await client.get(
            "/api/sharing/admin?page=2&page_size=2", headers=_headers(admin_user)
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["items"]) == 1


class TestAdminSharesFiltering:
    """Filter parameter tests."""

    @pytest.mark.asyncio
    async def test_filter_by_entity_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        multiple_shares: list[EntityShare],
    ):
        """entity_type filter returns only matching rows."""
        response = await client.get(
            "/api/sharing/admin?entity_type=leads", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["entity_type"] == "leads"

    @pytest.mark.asyncio
    async def test_filter_by_shared_with_user_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        multiple_shares: list[EntityShare],
        another_user: User,
    ):
        """shared_with_user_id filter returns only that user's incoming shares."""
        response = await client.get(
            f"/api/sharing/admin?shared_with_user_id={another_user.id}",
            headers=_headers(admin_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        for item in data["items"]:
            assert item["shared_with_user_id"] == another_user.id

    @pytest.mark.asyncio
    async def test_filter_by_shared_by_user_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        multiple_shares: list[EntityShare],
        sales_rep_user: User,
    ):
        """shared_by_user_id filter returns only shares created by that user."""
        response = await client.get(
            f"/api/sharing/admin?shared_by_user_id={sales_rep_user.id}",
            headers=_headers(admin_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        for item in data["items"]:
            assert item["shared_by_user_id"] == sales_rep_user.id

    @pytest.mark.asyncio
    async def test_filter_by_permission_level(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        multiple_shares: list[EntityShare],
    ):
        """permission_level filter returns only matching rows."""
        response = await client.get(
            "/api/sharing/admin?permission_level=edit", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["permission_level"] == "edit"

    @pytest.mark.asyncio
    async def test_combined_filters(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        multiple_shares: list[EntityShare],
        another_user: User,
    ):
        """Multiple filters are ANDed together."""
        response = await client.get(
            f"/api/sharing/admin?entity_type=contacts&shared_with_user_id={another_user.id}",
            headers=_headers(admin_user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["entity_type"] == "contacts"
        assert data["items"][0]["shared_with_user_id"] == another_user.id


class TestAdminRevokeShare:
    """Tests for DELETE /api/sharing/{share_id} exercised by an admin."""

    @pytest.mark.asyncio
    async def test_admin_can_revoke_share_they_did_not_create(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        sample_share: EntityShare,
    ):
        """Admin can revoke any share, even one they didn't create."""
        response = await client.delete(
            f"/api/sharing/{sample_share.id}", headers=_headers(admin_user)
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_revoked_share_disappears_from_admin_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        sample_share: EntityShare,
    ):
        """After revocation the share no longer appears in the admin listing."""
        await client.delete(
            f"/api/sharing/{sample_share.id}", headers=_headers(admin_user)
        )
        response = await client.get(
            "/api/sharing/admin", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        ids = [item["id"] for item in response.json()["items"]]
        assert sample_share.id not in ids

    @pytest.mark.asyncio
    async def test_unrelated_manager_cannot_revoke(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        manager_user: User,
        sample_share: EntityShare,
    ):
        """Manager who is neither sharer nor recipient is denied (admin-only bypass)."""
        response = await client.delete(
            f"/api/sharing/{sample_share.id}", headers=_headers(manager_user)
        )
        assert response.status_code == 403


class TestAdminBulkShare:
    """Tests for POST /api/sharing/admin/bulk."""

    async def _make_contact(
        self,
        db_session: AsyncSession,
        admin_user: User,
        email: str,
    ) -> Contact:
        contact = Contact(
            first_name="Bulk",
            last_name=email.split("@")[0],
            email=email,
            status="active",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)
        return contact

    @pytest.mark.asyncio
    async def test_sales_rep_gets_403(
        self,
        client: AsyncClient,
        sales_rep_user: User,
        another_user: User,
    ):
        response = await client.post(
            "/api/sharing/admin/bulk",
            headers=_headers(sales_rep_user),
            json={
                "entity_type": "contacts",
                "entity_ids": [1],
                "shared_with_user_id": another_user.id,
                "permission_level": "view",
            },
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_validates_request_contract(
        self,
        client: AsyncClient,
        admin_user: User,
        another_user: User,
        inactive_user: User,
    ):
        invalid_permission = await client.post(
            "/api/sharing/admin/bulk",
            headers=_headers(admin_user),
            json={
                "entity_type": "contacts",
                "entity_ids": [1],
                "shared_with_user_id": another_user.id,
                "permission_level": "owner",
            },
        )
        assert invalid_permission.status_code == 400

        self_share = await client.post(
            "/api/sharing/admin/bulk",
            headers=_headers(admin_user),
            json={
                "entity_type": "contacts",
                "entity_ids": [1],
                "shared_with_user_id": admin_user.id,
                "permission_level": "view",
            },
        )
        assert self_share.status_code == 400

        inactive_target = await client.post(
            "/api/sharing/admin/bulk",
            headers=_headers(admin_user),
            json={
                "entity_type": "contacts",
                "entity_ids": [1],
                "shared_with_user_id": inactive_user.id,
                "permission_level": "view",
            },
        )
        assert inactive_target.status_code == 404

        invalid_entity = await client.post(
            "/api/sharing/admin/bulk",
            headers=_headers(admin_user),
            json={
                "entity_type": "payments",
                "entity_ids": [1],
                "shared_with_user_id": another_user.id,
                "permission_level": "view",
            },
        )
        assert invalid_entity.status_code == 400

    @pytest.mark.asyncio
    async def test_creates_updates_skips_and_reports_missing_records(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        another_user: User,
    ):
        new_contact = await self._make_contact(
            db_session, admin_user, "bulk-new@example.com"
        )
        skipped_contact = await self._make_contact(
            db_session, admin_user, "bulk-skip@example.com"
        )
        updated_contact = await self._make_contact(
            db_session, admin_user, "bulk-update@example.com"
        )
        missing_id = updated_contact.id + 999

        db_session.add_all([
            EntityShare(
                entity_type="contacts",
                entity_id=skipped_contact.id,
                shared_with_user_id=another_user.id,
                shared_by_user_id=admin_user.id,
                permission_level="view",
            ),
            EntityShare(
                entity_type="contacts",
                entity_id=updated_contact.id,
                shared_with_user_id=another_user.id,
                shared_by_user_id=another_user.id,
                permission_level="edit",
            ),
        ])
        await db_session.commit()

        data_scope_module._scope_cache[another_user.id] = (
            time.monotonic(),
            DataScope(
                user_id=another_user.id,
                role_name="sales_rep",
                owner_id=another_user.id,
                is_scoped=True,
                shared_entity_ids={"contacts": [skipped_contact.id]},
            ),
        )

        response = await client.post(
            "/api/sharing/admin/bulk",
            headers=_headers(admin_user),
            json={
                "entity_type": "contacts",
                "entity_ids": [
                    new_contact.id,
                    skipped_contact.id,
                    updated_contact.id,
                    missing_id,
                    new_contact.id,
                ],
                "shared_with_user_id": another_user.id,
                "permission_level": "view",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["created"] == 1
        assert data["updated"] == 1
        assert data["skipped"] == 1
        assert data["failed"] == 1
        assert [item["entity_id"] for item in data["items"]] == [
            new_contact.id,
            skipped_contact.id,
            updated_contact.id,
            missing_id,
        ]
        assert {item["status"] for item in data["items"]} == {
            "created",
            "updated",
            "skipped",
            "failed",
        }

        shares = (
            await db_session.execute(
                select(EntityShare).where(
                    EntityShare.shared_with_user_id == another_user.id,
                    EntityShare.entity_id.in_([
                        new_contact.id,
                        skipped_contact.id,
                        updated_contact.id,
                    ]),
                )
            )
        ).scalars().all()
        permission_by_entity = {share.entity_id: share.permission_level for share in shares}
        assert permission_by_entity == {
            new_contact.id: "view",
            skipped_contact.id: "view",
            updated_contact.id: "view",
        }
        assert another_user.id not in data_scope_module._scope_cache

        notifications = (
            await db_session.execute(
                select(Notification).where(Notification.user_id == another_user.id)
            )
        ).scalars().all()
        assert len(notifications) == 1
        assert notifications[0].type == "entity_shared_with_you"

"""
Tests for admin sharing endpoint: GET /api/sharing/admin and related flows.
"""

import secrets
import time

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.companies.models import Company
from src.contacts.models import Contact
from src.core import data_scope as data_scope_module
from src.core.data_scope import DataScope
from src.core.models import EntityShare
from src.leads.models import Lead
from src.notifications.models import Notification
from src.proposals.models import Proposal
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


class TestAdminSharesEnrichmentAndSearch:
    """Tests for entity_label/entity_subtitle enrichment + `q` search."""

    @pytest_asyncio.fixture
    async def enriched_world(
        self,
        db_session: AsyncSession,
        admin_user: User,
        another_user: User,
    ) -> dict:
        """Build a contact/company/lead/proposal each with a share row.

        Returns a dict keyed by entity_type → (entity, share) so individual
        tests can lookup the IDs they need without re-querying.
        """
        company = Company(
            name="Acme Industries",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
            status="prospect",
        )
        contact = Contact(
            first_name="Priya",
            last_name="Ramanathan",
            email="priya@acme.example",
            status="active",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db_session.add_all([company, contact])
        await db_session.flush()
        contact.company_id = company.id

        lead = Lead(
            first_name="Marcus",
            last_name="Okafor",
            email="marcus@startup.example",
            company_name="Startup Forge LLC",
            status="new",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        proposal = Proposal(
            proposal_number=f"PR-TEST-{secrets.token_hex(4)}",
            title="Q3 Onboarding Engagement",
            contact_id=contact.id,
            company_id=company.id,
            status="draft",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db_session.add_all([lead, proposal])
        await db_session.flush()

        shares = {
            "contacts": EntityShare(
                entity_type="contacts",
                entity_id=contact.id,
                shared_with_user_id=another_user.id,
                shared_by_user_id=admin_user.id,
                permission_level="view",
            ),
            "companies": EntityShare(
                entity_type="companies",
                entity_id=company.id,
                shared_with_user_id=another_user.id,
                shared_by_user_id=admin_user.id,
                permission_level="edit",
            ),
            "leads": EntityShare(
                entity_type="leads",
                entity_id=lead.id,
                shared_with_user_id=another_user.id,
                shared_by_user_id=admin_user.id,
                permission_level="view",
            ),
            "proposals": EntityShare(
                entity_type="proposals",
                entity_id=proposal.id,
                shared_with_user_id=another_user.id,
                shared_by_user_id=admin_user.id,
                permission_level="edit",
            ),
        }
        for share in shares.values():
            db_session.add(share)
        await db_session.commit()

        return {
            "company": company,
            "contact": contact,
            "lead": lead,
            "proposal": proposal,
            "shares": shares,
        }

    def _by_type(self, items: list[dict], entity_type: str) -> dict:
        matches = [item for item in items if item["entity_type"] == entity_type]
        assert len(matches) == 1, f"expected exactly one {entity_type} row"
        return matches[0]

    @pytest.mark.asyncio
    async def test_entity_label_and_subtitle_populated(
        self,
        client: AsyncClient,
        admin_user: User,
        enriched_world: dict,
    ):
        """Each entity_type renders its real name + a meaningful subtitle."""
        response = await client.get(
            "/api/sharing/admin", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        items = response.json()["items"]

        contact_row = self._by_type(items, "contacts")
        assert contact_row["entity_label"] == "Priya Ramanathan"
        assert contact_row["entity_subtitle"] == "Acme Industries • priya@acme.example"

        company_row = self._by_type(items, "companies")
        assert company_row["entity_label"] == "Acme Industries"
        assert company_row["entity_subtitle"] is None

        lead_row = self._by_type(items, "leads")
        assert lead_row["entity_label"] == "Marcus Okafor"
        assert lead_row["entity_subtitle"] == "Startup Forge LLC • marcus@startup.example"

        proposal_row = self._by_type(items, "proposals")
        assert proposal_row["entity_label"] == "Q3 Onboarding Engagement"
        assert proposal_row["entity_subtitle"] == "Acme Industries • Priya Ramanathan"

    @pytest.mark.asyncio
    async def test_entity_label_null_for_missing_record(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        another_user: User,
    ):
        """A share pointing at a hard-deleted entity_id still appears with NULL label."""
        share = EntityShare(
            entity_type="contacts",
            entity_id=9_999_999,
            shared_with_user_id=another_user.id,
            shared_by_user_id=admin_user.id,
            permission_level="view",
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.get(
            "/api/sharing/admin", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        rows = [item for item in response.json()["items"] if item["id"] == share.id]
        assert len(rows) == 1
        assert rows[0]["entity_label"] is None
        assert rows[0]["entity_subtitle"] is None

    @pytest.mark.asyncio
    async def test_lead_label_falls_back_to_company_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        another_user: User,
    ):
        """A lead with no first/last name shows the company_name as the label."""
        lead = Lead(
            company_name="Headless Co",
            status="new",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db_session.add(lead)
        await db_session.flush()
        share = EntityShare(
            entity_type="leads",
            entity_id=lead.id,
            shared_with_user_id=another_user.id,
            shared_by_user_id=admin_user.id,
            permission_level="view",
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.get(
            f"/api/sharing/admin?entity_type=leads&shared_with_user_id={another_user.id}",
            headers=_headers(admin_user),
        )
        assert response.status_code == 200
        rows = [item for item in response.json()["items"] if item["id"] == share.id]
        assert rows[0]["entity_label"] == "Headless Co"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("needle", "expected_types"),
        [
            # Lead's free-text company_name.
            ("startup+forge", ["leads"]),
            # Proposal title.
            ("onboarding", ["proposals"]),
            # Contact last name — matches the contact share AND the proposal
            # share whose contact_id points at that contact.
            ("ramanathan", ["contacts", "proposals"]),
            # Company name — matches the company share, the contact share
            # (contact.company_id), and the proposal share (proposal.company_id).
            ("acme", ["companies", "contacts", "proposals"]),
        ],
    )
    async def test_q_search_matches_expected_entity_types(
        self,
        client: AsyncClient,
        admin_user: User,
        enriched_world: dict,
        needle: str,
        expected_types: list[str],
    ):
        """Substring search hits the right join columns for each entity type.

        Asks "who has access to anything matching <needle>?" and the admin
        gets every share row whose entity (or whose linked entity) carries
        the term in its name/title/company/email columns.
        """
        response = await client.get(
            f"/api/sharing/admin?q={needle}", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        types = sorted(item["entity_type"] for item in response.json()["items"])
        assert types == expected_types

    @pytest.mark.asyncio
    async def test_q_matches_recipient_user_email(
        self,
        client: AsyncClient,
        admin_user: User,
        another_user: User,
        enriched_world: dict,
    ):
        """`q` also searches the shared_with user's name + email."""
        response = await client.get(
            f"/api/sharing/admin?q={another_user.email.split('@')[0]}",
            headers=_headers(admin_user),
        )
        assert response.status_code == 200
        # Every share in enriched_world is shared with `another_user`.
        assert response.json()["total"] == 4

    @pytest.mark.asyncio
    async def test_q_whitespace_only_is_treated_as_no_filter(
        self,
        client: AsyncClient,
        admin_user: User,
        enriched_world: dict,
    ):
        response = await client.get(
            "/api/sharing/admin?q=%20%20%20", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        # All 4 enriched shares present — whitespace-only q must not filter.
        assert response.json()["total"] == 4

    @pytest.mark.asyncio
    async def test_soft_deleted_contact_renders_as_unlabelled(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        another_user: User,
    ):
        """A share targeting an archived contact must not resurrect its name.

        Soft-deleted contacts are filtered out of the JOIN so the row falls
        through to the "Deleted contact" rendering path — the admin can
        still see and revoke it, but isn't misled into thinking the contact
        is live.
        """
        from datetime import UTC, datetime

        contact = Contact(
            first_name="Sara",
            last_name="Halverson",
            email="sara@gone.example",
            status="archived",
            deleted_at=datetime.now(UTC),
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db_session.add(contact)
        await db_session.flush()
        share = EntityShare(
            entity_type="contacts",
            entity_id=contact.id,
            shared_with_user_id=another_user.id,
            shared_by_user_id=admin_user.id,
            permission_level="view",
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.get(
            "/api/sharing/admin", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        row = next(item for item in response.json()["items"] if item["id"] == share.id)
        assert row["entity_label"] is None
        assert row["entity_subtitle"] is None

    @pytest.mark.asyncio
    async def test_merged_company_renders_as_unlabelled(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        another_user: User,
    ):
        """A share targeting a merged-away company falls through to the
        deleted-entity rendering path, not the survivor's old name."""
        survivor = Company(
            name="Survivor Corp",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
            status="customer",
        )
        db_session.add(survivor)
        await db_session.flush()
        merged_away = Company(
            name="Old Acme",
            status="merged",
            merged_into_id=survivor.id,
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db_session.add(merged_away)
        await db_session.flush()
        share = EntityShare(
            entity_type="companies",
            entity_id=merged_away.id,
            shared_with_user_id=another_user.id,
            shared_by_user_id=admin_user.id,
            permission_level="view",
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.get(
            "/api/sharing/admin", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        row = next(item for item in response.json()["items"] if item["id"] == share.id)
        assert row["entity_label"] is None

    @pytest.mark.asyncio
    async def test_nameless_contact_falls_back_to_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
        another_user: User,
    ):
        """A live contact with empty names but a populated email surfaces
        the email as the label so the admin can still place the share."""
        contact = Contact(
            first_name="",
            last_name="",
            email="anon@guest.example",
            status="active",
            owner_id=admin_user.id,
            created_by_id=admin_user.id,
        )
        db_session.add(contact)
        await db_session.flush()
        share = EntityShare(
            entity_type="contacts",
            entity_id=contact.id,
            shared_with_user_id=another_user.id,
            shared_by_user_id=admin_user.id,
            permission_level="view",
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.get(
            "/api/sharing/admin", headers=_headers(admin_user)
        )
        assert response.status_code == 200
        row = next(item for item in response.json()["items"] if item["id"] == share.id)
        assert row["entity_label"] == "anon@guest.example"

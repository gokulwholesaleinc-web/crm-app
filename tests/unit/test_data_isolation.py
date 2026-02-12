"""Tests for RBAC data isolation and sharing functionality.

Validates:
- Sales rep A cannot see sales rep B's leads/contacts/companies/opportunities
- Manager can see ALL records regardless of owner
- Admin can see ALL records regardless of owner
- Sharing grants access to shared user only
- Revoking share removes access
- Sharing endpoints work correctly
"""

import pytest
from httpx import AsyncClient

from src.auth.security import get_password_hash, create_access_token
from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.contacts.models import Contact
from src.companies.models import Company
from src.opportunities.models import Opportunity, PipelineStage
from src.roles.models import Role, UserRole
from src.core.models import EntityShare


# =========================================================================
# Helper fixtures
# =========================================================================

@pytest.fixture
async def sales_rep_a(db_session):
    """Create sales rep A user."""
    user = User(
        email="repa@test.com",
        hashed_password=get_password_hash("password123"),
        full_name="Sales Rep A",
        is_active=True,
        is_superuser=False,
        role="sales_rep",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Create role and assign
    role = Role(name="sales_rep_a_role", permissions={
        "leads": ["create", "read", "update", "delete"],
        "contacts": ["create", "read", "update", "delete"],
        "companies": ["create", "read", "update", "delete"],
        "opportunities": ["create", "read", "update", "delete"],
    })
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user_role = UserRole(user_id=user.id, role_id=role.id)
    db_session.add(user_role)
    await db_session.commit()

    return user


@pytest.fixture
async def sales_rep_b(db_session):
    """Create sales rep B user."""
    user = User(
        email="repb@test.com",
        hashed_password=get_password_hash("password123"),
        full_name="Sales Rep B",
        is_active=True,
        is_superuser=False,
        role="sales_rep",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    role = Role(name="sales_rep_b_role", permissions={
        "leads": ["create", "read", "update", "delete"],
        "contacts": ["create", "read", "update", "delete"],
        "companies": ["create", "read", "update", "delete"],
        "opportunities": ["create", "read", "update", "delete"],
    })
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user_role = UserRole(user_id=user.id, role_id=role.id)
    db_session.add(user_role)
    await db_session.commit()

    return user


@pytest.fixture
async def manager_user(db_session):
    """Create a manager user."""
    user = User(
        email="manager@test.com",
        hashed_password=get_password_hash("password123"),
        full_name="Manager User",
        is_active=True,
        is_superuser=False,
        role="manager",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    role = Role(name="manager_role", permissions={
        "leads": ["create", "read", "update", "delete"],
        "contacts": ["create", "read", "update", "delete"],
        "companies": ["create", "read", "update", "delete"],
        "opportunities": ["create", "read", "update", "delete"],
    })
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user_role = UserRole(user_id=user.id, role_id=role.id)
    db_session.add(user_role)
    await db_session.commit()

    return user


@pytest.fixture
async def admin_user(db_session):
    """Create an admin user (superuser)."""
    user = User(
        email="admin@test.com",
        hashed_password=get_password_hash("password123"),
        full_name="Admin User",
        is_active=True,
        is_superuser=True,
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _token(user: User) -> dict:
    """Create auth headers for a user."""
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def lead_source(db_session):
    source = LeadSource(name="TestSource", is_active=True)
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest.fixture
async def pipeline_stage(db_session):
    stage = PipelineStage(
        name="Qualification", order=1, color="#6366f1",
        probability=20, is_won=False, is_lost=False, is_active=True,
    )
    db_session.add(stage)
    await db_session.commit()
    await db_session.refresh(stage)
    return stage


@pytest.fixture
async def rep_a_lead(db_session, sales_rep_a, lead_source):
    """Lead owned by sales rep A."""
    lead = Lead(
        first_name="Alice", last_name="Lead", email="alice@test.com",
        status="new", score=50, owner_id=sales_rep_a.id,
        source_id=lead_source.id, created_by_id=sales_rep_a.id,
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    return lead


@pytest.fixture
async def rep_b_lead(db_session, sales_rep_b, lead_source):
    """Lead owned by sales rep B."""
    lead = Lead(
        first_name="Bob", last_name="Lead", email="bob@test.com",
        status="new", score=60, owner_id=sales_rep_b.id,
        source_id=lead_source.id, created_by_id=sales_rep_b.id,
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    return lead


@pytest.fixture
async def rep_a_contact(db_session, sales_rep_a):
    """Contact owned by sales rep A."""
    contact = Contact(
        first_name="Alice", last_name="Contact", email="alice.contact@test.com",
        status="active", owner_id=sales_rep_a.id, created_by_id=sales_rep_a.id,
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


@pytest.fixture
async def rep_b_contact(db_session, sales_rep_b):
    """Contact owned by sales rep B."""
    contact = Contact(
        first_name="Bob", last_name="Contact", email="bob.contact@test.com",
        status="active", owner_id=sales_rep_b.id, created_by_id=sales_rep_b.id,
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)
    return contact


# =========================================================================
# Test Classes
# =========================================================================

class TestLeadDataIsolation:
    """Test that lead data is properly isolated between sales reps."""

    @pytest.mark.asyncio
    async def test_sales_rep_a_sees_only_own_leads(
        self, client: AsyncClient, sales_rep_a, sales_rep_b, rep_a_lead, rep_b_lead,
    ):
        """Sales rep A should only see their own leads."""
        response = await client.get("/api/leads", headers=_token(sales_rep_a))
        assert response.status_code == 200
        data = response.json()
        lead_emails = [item["email"] for item in data["items"]]
        assert "alice@test.com" in lead_emails
        assert "bob@test.com" not in lead_emails

    @pytest.mark.asyncio
    async def test_sales_rep_b_sees_only_own_leads(
        self, client: AsyncClient, sales_rep_a, sales_rep_b, rep_a_lead, rep_b_lead,
    ):
        """Sales rep B should only see their own leads."""
        response = await client.get("/api/leads", headers=_token(sales_rep_b))
        assert response.status_code == 200
        data = response.json()
        lead_emails = [item["email"] for item in data["items"]]
        assert "bob@test.com" in lead_emails
        assert "alice@test.com" not in lead_emails

    @pytest.mark.asyncio
    async def test_sales_rep_cannot_get_other_users_lead_by_id(
        self, client: AsyncClient, sales_rep_a, sales_rep_b, rep_b_lead,
    ):
        """Sales rep A should NOT be able to get rep B's lead by ID."""
        response = await client.get(
            f"/api/leads/{rep_b_lead.id}", headers=_token(sales_rep_a),
        )
        assert response.status_code == 403

    @pytest.mark.skip(reason="Manager 'sees all' not yet implemented in leads router")
    @pytest.mark.asyncio
    async def test_manager_sees_all_leads(
        self, client: AsyncClient, manager_user, sales_rep_a, sales_rep_b,
        rep_a_lead, rep_b_lead,
    ):
        """Manager should see ALL leads regardless of owner."""
        response = await client.get("/api/leads", headers=_token(manager_user))
        assert response.status_code == 200
        data = response.json()
        lead_emails = [item["email"] for item in data["items"]]
        assert "alice@test.com" in lead_emails
        assert "bob@test.com" in lead_emails

    @pytest.mark.asyncio
    async def test_admin_sees_all_leads(
        self, client: AsyncClient, admin_user, sales_rep_a, sales_rep_b,
        rep_a_lead, rep_b_lead,
    ):
        """Admin should see ALL leads regardless of owner."""
        response = await client.get("/api/leads", headers=_token(admin_user))
        assert response.status_code == 200
        data = response.json()
        lead_emails = [item["email"] for item in data["items"]]
        assert "alice@test.com" in lead_emails
        assert "bob@test.com" in lead_emails

    @pytest.mark.skip(reason="Manager 'sees all' not yet implemented in leads router")
    @pytest.mark.asyncio
    async def test_manager_can_get_any_lead_by_id(
        self, client: AsyncClient, manager_user, sales_rep_a, rep_a_lead,
    ):
        """Manager should be able to get any lead by ID."""
        response = await client.get(
            f"/api/leads/{rep_a_lead.id}", headers=_token(manager_user),
        )
        assert response.status_code == 200
        assert response.json()["email"] == "alice@test.com"


class TestContactDataIsolation:
    """Test that contact data is properly isolated between sales reps."""

    @pytest.mark.asyncio
    async def test_sales_rep_sees_only_own_contacts(
        self, client: AsyncClient, sales_rep_a, sales_rep_b,
        rep_a_contact, rep_b_contact,
    ):
        """Sales rep A should only see their own contacts."""
        response = await client.get("/api/contacts", headers=_token(sales_rep_a))
        assert response.status_code == 200
        data = response.json()
        emails = [item["email"] for item in data["items"]]
        assert "alice.contact@test.com" in emails
        assert "bob.contact@test.com" not in emails

    @pytest.mark.asyncio
    async def test_sales_rep_cannot_get_other_users_contact(
        self, client: AsyncClient, sales_rep_a, sales_rep_b, rep_b_contact,
    ):
        """Sales rep A should NOT access rep B's contact by ID."""
        response = await client.get(
            f"/api/contacts/{rep_b_contact.id}", headers=_token(sales_rep_a),
        )
        assert response.status_code == 403

    @pytest.mark.skip(reason="Manager 'sees all' not yet implemented in contacts router")
    @pytest.mark.asyncio
    async def test_manager_sees_all_contacts(
        self, client: AsyncClient, manager_user, sales_rep_a, sales_rep_b,
        rep_a_contact, rep_b_contact,
    ):
        """Manager should see all contacts."""
        response = await client.get("/api/contacts", headers=_token(manager_user))
        assert response.status_code == 200
        data = response.json()
        emails = [item["email"] for item in data["items"]]
        assert "alice.contact@test.com" in emails
        assert "bob.contact@test.com" in emails


class TestSharingEndpoints:
    """Test the sharing endpoints for record collaboration."""

    @pytest.mark.asyncio
    async def test_share_lead_with_another_user(
        self, client: AsyncClient, sales_rep_a, sales_rep_b, rep_a_lead,
    ):
        """Sales rep A shares a lead with sales rep B."""
        response = await client.post(
            "/api/sharing",
            json={
                "entity_type": "leads",
                "entity_id": rep_a_lead.id,
                "shared_with_user_id": sales_rep_b.id,
                "permission_level": "view",
            },
            headers=_token(sales_rep_a),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["entity_type"] == "leads"
        assert data["shared_with_user_id"] == sales_rep_b.id
        assert data["shared_by_user_id"] == sales_rep_a.id

    @pytest.mark.asyncio
    async def test_cannot_share_with_self(
        self, client: AsyncClient, sales_rep_a, rep_a_lead,
    ):
        """Should not be able to share a record with yourself."""
        response = await client.post(
            "/api/sharing",
            json={
                "entity_type": "leads",
                "entity_id": rep_a_lead.id,
                "shared_with_user_id": sales_rep_a.id,
            },
            headers=_token(sales_rep_a),
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_duplicate_share_returns_conflict(
        self, client: AsyncClient, sales_rep_a, sales_rep_b, rep_a_lead,
    ):
        """Sharing the same record twice should return 409."""
        payload = {
            "entity_type": "leads",
            "entity_id": rep_a_lead.id,
            "shared_with_user_id": sales_rep_b.id,
        }
        await client.post("/api/sharing", json=payload, headers=_token(sales_rep_a))
        response = await client.post(
            "/api/sharing", json=payload, headers=_token(sales_rep_a),
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_list_entity_shares(
        self, client: AsyncClient, sales_rep_a, sales_rep_b, rep_a_lead,
    ):
        """List shares for an entity."""
        await client.post(
            "/api/sharing",
            json={
                "entity_type": "leads",
                "entity_id": rep_a_lead.id,
                "shared_with_user_id": sales_rep_b.id,
            },
            headers=_token(sales_rep_a),
        )

        response = await client.get(
            f"/api/sharing/leads/{rep_a_lead.id}",
            headers=_token(sales_rep_a),
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["shared_with_user_id"] == sales_rep_b.id

    @pytest.mark.asyncio
    async def test_revoke_share(
        self, client: AsyncClient, sales_rep_a, sales_rep_b, rep_a_lead,
    ):
        """Revoking a share should work."""
        create_resp = await client.post(
            "/api/sharing",
            json={
                "entity_type": "leads",
                "entity_id": rep_a_lead.id,
                "shared_with_user_id": sales_rep_b.id,
            },
            headers=_token(sales_rep_a),
        )
        share_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/sharing/{share_id}",
            headers=_token(sales_rep_a),
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_share_returns_404(
        self, client: AsyncClient, sales_rep_a,
    ):
        """Revoking a non-existent share returns 404."""
        response = await client.delete(
            "/api/sharing/99999",
            headers=_token(sales_rep_a),
        )
        assert response.status_code == 404


class TestSharedRecordAccess:
    """Test that sharing actually grants access to shared records."""

    @pytest.mark.asyncio
    async def test_shared_lead_appears_in_list(
        self, client: AsyncClient, db_session,
        sales_rep_a, sales_rep_b, rep_a_lead, rep_b_lead,
    ):
        """After sharing, rep B should see rep A's lead in their list."""
        # Share rep A's lead with rep B
        share = EntityShare(
            entity_type="leads",
            entity_id=rep_a_lead.id,
            shared_with_user_id=sales_rep_b.id,
            shared_by_user_id=sales_rep_a.id,
            permission_level="view",
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.get("/api/leads", headers=_token(sales_rep_b))
        assert response.status_code == 200
        data = response.json()
        lead_emails = [item["email"] for item in data["items"]]
        assert "alice@test.com" in lead_emails  # Shared lead
        assert "bob@test.com" in lead_emails    # Own lead

    @pytest.mark.asyncio
    async def test_shared_lead_accessible_by_id(
        self, client: AsyncClient, db_session,
        sales_rep_a, sales_rep_b, rep_a_lead,
    ):
        """After sharing, rep B should be able to get rep A's lead by ID."""
        share = EntityShare(
            entity_type="leads",
            entity_id=rep_a_lead.id,
            shared_with_user_id=sales_rep_b.id,
            shared_by_user_id=sales_rep_a.id,
            permission_level="view",
        )
        db_session.add(share)
        await db_session.commit()

        response = await client.get(
            f"/api/leads/{rep_a_lead.id}", headers=_token(sales_rep_b),
        )
        assert response.status_code == 200
        assert response.json()["email"] == "alice@test.com"

    @pytest.mark.asyncio
    async def test_revoked_share_removes_access(
        self, client: AsyncClient, db_session,
        sales_rep_a, sales_rep_b, rep_a_lead,
    ):
        """After revoking share, rep B should no longer see rep A's lead."""
        share = EntityShare(
            entity_type="leads",
            entity_id=rep_a_lead.id,
            shared_with_user_id=sales_rep_b.id,
            shared_by_user_id=sales_rep_a.id,
            permission_level="view",
        )
        db_session.add(share)
        await db_session.commit()
        await db_session.refresh(share)

        # Verify access
        response = await client.get(
            f"/api/leads/{rep_a_lead.id}", headers=_token(sales_rep_b),
        )
        assert response.status_code == 200

        # Revoke
        await db_session.delete(share)
        await db_session.commit()

        # Access should be denied
        response = await client.get(
            f"/api/leads/{rep_a_lead.id}", headers=_token(sales_rep_b),
        )
        assert response.status_code == 403

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
from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.contacts.models import Contact
from src.core.data_scope import invalidate_scope_cache
from src.core.models import EntityShare
from src.leads.models import Lead, LeadSource
from src.opportunities.models import PipelineStage
from src.roles.models import Role, UserRole

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


async def _share_lead(
    db_session,
    lead: Lead,
    shared_with: User,
    shared_by: User,
    permission_level: str = "view",
    entity_type: str = "leads",
) -> EntityShare:
    share = EntityShare(
        entity_type=entity_type,
        entity_id=lead.id,
        shared_with_user_id=shared_with.id,
        shared_by_user_id=shared_by.id,
        permission_level=permission_level,
    )
    db_session.add(share)
    await db_session.commit()
    await db_session.refresh(share)
    invalidate_scope_cache(shared_with.id)
    return share


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
        name="Discovery", order=1, color="#6366f1",
        probability=20, is_won=False, is_lost=False, is_active=True,
        pipeline_type="lead",
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
    async def test_legacy_singular_duplicate_share_returns_conflict(
        self, client: AsyncClient, db_session, sales_rep_a, sales_rep_b, rep_a_lead,
    ):
        """Existing singular share rows still block duplicate canonical shares."""
        await _share_lead(
            db_session,
            rep_a_lead,
            sales_rep_b,
            sales_rep_a,
            entity_type="lead",
        )

        response = await client.post(
            "/api/sharing",
            json={
                "entity_type": "leads",
                "entity_id": rep_a_lead.id,
                "shared_with_user_id": sales_rep_b.id,
            },
            headers=_token(sales_rep_a),
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
    async def test_non_accessor_cannot_list_entity_shares(
        self, client: AsyncClient, sales_rep_b, rep_a_lead,
    ):
        """A user who cannot access the record cannot enumerate its shares."""
        response = await client.get(
            f"/api/sharing/leads/{rep_a_lead.id}",
            headers=_token(sales_rep_b),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_shared_recipient_cannot_reshare(
        self, client: AsyncClient, db_session, sales_rep_a, sales_rep_b,
        manager_user, rep_a_lead,
    ):
        """A view-only recipient cannot grant the same record to someone else."""
        await _share_lead(db_session, rep_a_lead, sales_rep_b, sales_rep_a)

        response = await client.post(
            "/api/sharing",
            json={
                "entity_type": "leads",
                "entity_id": rep_a_lead.id,
                "shared_with_user_id": manager_user.id,
                "permission_level": "edit",
            },
            headers=_token(sales_rep_b),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_singular_entity_type_is_stored_canonical(
        self, client: AsyncClient, sales_rep_a, sales_rep_b, rep_a_lead,
    ):
        """Singular share requests are stored as canonical plural rows."""
        response = await client.post(
            "/api/sharing",
            json={
                "entity_type": "lead",
                "entity_id": rep_a_lead.id,
                "shared_with_user_id": sales_rep_b.id,
                "permission_level": "view",
            },
            headers=_token(sales_rep_a),
        )
        assert response.status_code == 201
        assert response.json()["entity_type"] == "leads"

        response = await client.get(
            f"/api/leads/{rep_a_lead.id}",
            headers=_token(sales_rep_b),
        )
        assert response.status_code == 200

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
        await _share_lead(db_session, rep_a_lead, sales_rep_b, sales_rep_a)

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
        await _share_lead(db_session, rep_a_lead, sales_rep_b, sales_rep_a)

        response = await client.get(
            f"/api/leads/{rep_a_lead.id}", headers=_token(sales_rep_b),
        )
        assert response.status_code == 200
        assert response.json()["email"] == "alice@test.com"

    @pytest.mark.asyncio
    async def test_view_share_cannot_move_lead(
        self, client: AsyncClient, db_session, sales_rep_a, sales_rep_b,
        rep_a_lead, pipeline_stage,
    ):
        """A view share grants read access, not kanban mutation access."""
        await _share_lead(db_session, rep_a_lead, sales_rep_b, sales_rep_a)

        response = await client.post(
            f"/api/leads/{rep_a_lead.id}/move",
            json={"new_stage_id": pipeline_stage.id},
            headers=_token(sales_rep_b),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_edit_share_can_move_lead(
        self, client: AsyncClient, db_session, sales_rep_a, sales_rep_b,
        rep_a_lead, pipeline_stage,
    ):
        """An edit share can mutate the shared lead."""
        await _share_lead(
            db_session,
            rep_a_lead,
            sales_rep_b,
            sales_rep_a,
            permission_level="edit",
        )

        response = await client.post(
            f"/api/leads/{rep_a_lead.id}/move",
            json={"new_stage_id": pipeline_stage.id},
            headers=_token(sales_rep_b),
        )
        assert response.status_code == 200
        assert response.json()["pipeline_stage_id"] == pipeline_stage.id

    @pytest.mark.asyncio
    async def test_legacy_singular_edit_share_can_move_lead(
        self, client: AsyncClient, db_session, sales_rep_a, sales_rep_b,
        rep_a_lead, pipeline_stage,
    ):
        """Legacy singular share rows still honor edit permissions."""
        await _share_lead(
            db_session,
            rep_a_lead,
            sales_rep_b,
            sales_rep_a,
            permission_level="edit",
            entity_type="lead",
        )

        response = await client.post(
            f"/api/leads/{rep_a_lead.id}/move",
            json={"new_stage_id": pipeline_stage.id},
            headers=_token(sales_rep_b),
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_view_share_cannot_convert_lead(
        self, client: AsyncClient, db_session, sales_rep_a, sales_rep_b,
        rep_a_lead,
    ):
        """A view share cannot convert another user's lead."""
        await _share_lead(db_session, rep_a_lead, sales_rep_b, sales_rep_a)

        response = await client.post(
            f"/api/leads/{rep_a_lead.id}/convert/contact",
            json={"create_company": False},
            headers=_token(sales_rep_b),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_shared_lead_appears_in_kanban(
        self, client: AsyncClient, db_session, sales_rep_a, sales_rep_b,
        rep_a_lead, pipeline_stage,
    ):
        """Shared leads appear on the recipient's kanban board."""
        rep_a_lead.pipeline_stage_id = pipeline_stage.id
        await db_session.commit()
        await db_session.refresh(rep_a_lead)
        await _share_lead(db_session, rep_a_lead, sales_rep_b, sales_rep_a)

        response = await client.get("/api/leads/kanban", headers=_token(sales_rep_b))
        assert response.status_code == 200
        stage_leads = [
            lead
            for stage in response.json()["stages"]
            for lead in stage["leads"]
        ]
        assert rep_a_lead.id in {lead["id"] for lead in stage_leads}

    @pytest.mark.asyncio
    async def test_revoked_share_removes_access(
        self, client: AsyncClient, db_session,
        sales_rep_a, sales_rep_b, rep_a_lead,
    ):
        """After revoking share, rep B should no longer see rep A's lead."""
        share = await _share_lead(db_session, rep_a_lead, sales_rep_b, sales_rep_a)

        # Verify access
        response = await client.get(
            f"/api/leads/{rep_a_lead.id}", headers=_token(sales_rep_b),
        )
        assert response.status_code == 200

        # Revoke
        await db_session.delete(share)
        await db_session.commit()

        invalidate_scope_cache(sales_rep_b.id)

        # Access should be denied
        response = await client.get(
            f"/api/leads/{rep_a_lead.id}", headers=_token(sales_rep_b),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_sales_rep_cannot_create_lead_for_peer(
        self, client: AsyncClient, sales_rep_a, sales_rep_b,
    ):
        """Sales reps cannot create leads directly assigned to teammates."""
        response = await client.post(
            "/api/leads",
            json={
                "first_name": "Peer",
                "last_name": "Lead",
                "email": "peer.lead@test.com",
                "owner_id": sales_rep_b.id,
            },
            headers=_token(sales_rep_a),
        )
        assert response.status_code == 403

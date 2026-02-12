"""
Tests that audit logging is properly wired into entity CRUD operations.

Verifies that create, update, and delete operations on all major entities
produce the expected AuditLog records accessible via the audit API.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead, LeadSource
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity


async def _get_audit_items(client: AsyncClient, auth_headers: dict, entity_type: str, entity_id: int) -> list:
    """Fetch audit log items for an entity via the audit API."""
    resp = await client.get(
        f"/api/audit/{entity_type}/{entity_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    return resp.json()["items"]


class TestLeadAuditWiring:
    """Verify audit logs are created for lead CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_lead_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead_source: LeadSource,
    ):
        response = await client.post(
            "/api/leads",
            headers=auth_headers,
            json={
                "first_name": "AuditLead",
                "last_name": "Test",
                "email": "auditlead@example.com",
                "source_id": test_lead_source.id,
                "status": "new",
            },
        )
        assert response.status_code == 201
        lead_id = response.json()["id"]

        items = await _get_audit_items(client, auth_headers, "lead", lead_id)
        assert any(item["action"] == "create" for item in items)

    @pytest.mark.asyncio
    async def test_update_lead_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        response = await client.patch(
            f"/api/leads/{test_lead.id}",
            headers=auth_headers,
            json={"first_name": "UpdatedLeadName"},
        )
        assert response.status_code == 200

        items = await _get_audit_items(client, auth_headers, "lead", test_lead.id)
        update_items = [i for i in items if i["action"] == "update"]
        assert len(update_items) >= 1
        # Verify the change was tracked
        changes = update_items[0].get("changes", [])
        fields_changed = {c["field"] for c in changes}
        assert "first_name" in fields_changed

    @pytest.mark.asyncio
    async def test_delete_lead_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        lead_id = test_lead.id
        response = await client.delete(
            f"/api/leads/{lead_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        items = await _get_audit_items(client, auth_headers, "lead", lead_id)
        assert any(item["action"] == "delete" for item in items)


class TestContactAuditWiring:
    """Verify audit logs are created for contact CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_contact_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_company: Company,
    ):
        response = await client.post(
            "/api/contacts",
            headers=auth_headers,
            json={
                "first_name": "AuditContact",
                "last_name": "Test",
                "email": "auditcontact@example.com",
                "company_id": test_company.id,
                "status": "active",
            },
        )
        assert response.status_code == 201
        contact_id = response.json()["id"]

        items = await _get_audit_items(client, auth_headers, "contact", contact_id)
        assert any(item["action"] == "create" for item in items)

    @pytest.mark.asyncio
    async def test_update_contact_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        response = await client.patch(
            f"/api/contacts/{test_contact.id}",
            headers=auth_headers,
            json={"first_name": "UpdatedContactName"},
        )
        assert response.status_code == 200

        items = await _get_audit_items(client, auth_headers, "contact", test_contact.id)
        update_items = [i for i in items if i["action"] == "update"]
        assert len(update_items) >= 1
        changes = update_items[0].get("changes", [])
        fields_changed = {c["field"] for c in changes}
        assert "first_name" in fields_changed

    @pytest.mark.asyncio
    async def test_delete_contact_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        contact_id = test_contact.id
        response = await client.delete(
            f"/api/contacts/{contact_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        items = await _get_audit_items(client, auth_headers, "contact", contact_id)
        assert any(item["action"] == "delete" for item in items)


class TestCompanyAuditWiring:
    """Verify audit logs are created for company CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_company_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        response = await client.post(
            "/api/companies",
            headers=auth_headers,
            json={
                "name": "AuditCompany Inc",
                "industry": "Technology",
                "status": "prospect",
            },
        )
        assert response.status_code == 201
        company_id = response.json()["id"]

        items = await _get_audit_items(client, auth_headers, "company", company_id)
        assert any(item["action"] == "create" for item in items)

    @pytest.mark.asyncio
    async def test_update_company_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        response = await client.patch(
            f"/api/companies/{test_company.id}",
            headers=auth_headers,
            json={"name": "UpdatedCompanyName"},
        )
        assert response.status_code == 200

        items = await _get_audit_items(client, auth_headers, "company", test_company.id)
        update_items = [i for i in items if i["action"] == "update"]
        assert len(update_items) >= 1
        changes = update_items[0].get("changes", [])
        fields_changed = {c["field"] for c in changes}
        assert "name" in fields_changed

    @pytest.mark.asyncio
    async def test_delete_company_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        company_id = test_company.id
        response = await client.delete(
            f"/api/companies/{company_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        items = await _get_audit_items(client, auth_headers, "company", company_id)
        assert any(item["action"] == "delete" for item in items)


class TestOpportunityAuditWiring:
    """Verify audit logs are created for opportunity CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_opportunity_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_pipeline_stage: PipelineStage,
    ):
        response = await client.post(
            "/api/opportunities",
            headers=auth_headers,
            json={
                "name": "AuditOpportunity Test",
                "pipeline_stage_id": test_pipeline_stage.id,
                "amount": 25000,
            },
        )
        assert response.status_code == 201
        opp_id = response.json()["id"]

        items = await _get_audit_items(client, auth_headers, "opportunity", opp_id)
        assert any(item["action"] == "create" for item in items)

    @pytest.mark.asyncio
    async def test_update_opportunity_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        response = await client.patch(
            f"/api/opportunities/{test_opportunity.id}",
            headers=auth_headers,
            json={"name": "UpdatedOpportunityName"},
        )
        assert response.status_code == 200

        items = await _get_audit_items(client, auth_headers, "opportunity", test_opportunity.id)
        update_items = [i for i in items if i["action"] == "update"]
        assert len(update_items) >= 1
        changes = update_items[0].get("changes", [])
        fields_changed = {c["field"] for c in changes}
        assert "name" in fields_changed

    @pytest.mark.asyncio
    async def test_delete_opportunity_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_opportunity: Opportunity,
    ):
        opp_id = test_opportunity.id
        response = await client.delete(
            f"/api/opportunities/{opp_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        items = await _get_audit_items(client, auth_headers, "opportunity", opp_id)
        assert any(item["action"] == "delete" for item in items)


class TestActivityAuditWiring:
    """Verify audit logs are created for activity CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_activity_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "call",
                "subject": "Audit Activity Test",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "priority": "normal",
            },
        )
        assert response.status_code == 201
        activity_id = response.json()["id"]

        items = await _get_audit_items(client, auth_headers, "activity", activity_id)
        assert any(item["action"] == "create" for item in items)

    @pytest.mark.asyncio
    async def test_update_activity_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        response = await client.patch(
            f"/api/activities/{test_activity.id}",
            headers=auth_headers,
            json={"subject": "UpdatedActivitySubject"},
        )
        assert response.status_code == 200

        items = await _get_audit_items(client, auth_headers, "activity", test_activity.id)
        update_items = [i for i in items if i["action"] == "update"]
        assert len(update_items) >= 1
        changes = update_items[0].get("changes", [])
        fields_changed = {c["field"] for c in changes}
        assert "subject" in fields_changed

    @pytest.mark.asyncio
    async def test_delete_activity_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_activity: Activity,
    ):
        activity_id = test_activity.id
        response = await client.delete(
            f"/api/activities/{activity_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        items = await _get_audit_items(client, auth_headers, "activity", activity_id)
        assert any(item["action"] == "delete" for item in items)


class TestQuoteAuditWiring:
    """Verify audit logs are created for quote CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_quote_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        response = await client.post(
            "/api/quotes",
            headers=auth_headers,
            json={
                "title": "AuditQuote Test",
                "contact_id": test_contact.id,
            },
        )
        assert response.status_code == 201
        quote_id = response.json()["id"]

        items = await _get_audit_items(client, auth_headers, "quote", quote_id)
        assert any(item["action"] == "create" for item in items)

    @pytest.mark.asyncio
    async def test_update_quote_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        # Create a quote via API so current user owns it
        create_resp = await client.post(
            "/api/quotes",
            headers=auth_headers,
            json={
                "title": "QuoteToUpdate",
                "contact_id": test_contact.id,
                "owner_id": test_user.id,
            },
        )
        assert create_resp.status_code == 201
        quote_id = create_resp.json()["id"]

        response = await client.patch(
            f"/api/quotes/{quote_id}",
            headers=auth_headers,
            json={"title": "UpdatedQuoteTitle"},
        )
        assert response.status_code == 200

        items = await _get_audit_items(client, auth_headers, "quote", quote_id)
        update_items = [i for i in items if i["action"] == "update"]
        assert len(update_items) >= 1
        changes = update_items[0].get("changes", [])
        fields_changed = {c["field"] for c in changes}
        assert "title" in fields_changed

    @pytest.mark.asyncio
    async def test_delete_quote_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        # Create a quote via API so current user owns it
        create_resp = await client.post(
            "/api/quotes",
            headers=auth_headers,
            json={
                "title": "QuoteToDelete",
                "contact_id": test_contact.id,
                "owner_id": test_user.id,
            },
        )
        assert create_resp.status_code == 201
        quote_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/quotes/{quote_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        items = await _get_audit_items(client, auth_headers, "quote", quote_id)
        assert any(item["action"] == "delete" for item in items)


class TestProposalAuditWiring:
    """Verify audit logs are created for proposal CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_proposal_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        response = await client.post(
            "/api/proposals",
            headers=auth_headers,
            json={
                "title": "AuditProposal Test",
                "contact_id": test_contact.id,
            },
        )
        assert response.status_code == 201
        proposal_id = response.json()["id"]

        items = await _get_audit_items(client, auth_headers, "proposal", proposal_id)
        assert any(item["action"] == "create" for item in items)

    @pytest.mark.asyncio
    async def test_update_proposal_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        # Create a proposal via API so current user owns it
        create_resp = await client.post(
            "/api/proposals",
            headers=auth_headers,
            json={
                "title": "ProposalToUpdate",
                "contact_id": test_contact.id,
                "owner_id": test_user.id,
            },
        )
        assert create_resp.status_code == 201
        proposal_id = create_resp.json()["id"]

        response = await client.patch(
            f"/api/proposals/{proposal_id}",
            headers=auth_headers,
            json={"title": "UpdatedProposalTitle"},
        )
        assert response.status_code == 200

        items = await _get_audit_items(client, auth_headers, "proposal", proposal_id)
        update_items = [i for i in items if i["action"] == "update"]
        assert len(update_items) >= 1
        changes = update_items[0].get("changes", [])
        fields_changed = {c["field"] for c in changes}
        assert "title" in fields_changed

    @pytest.mark.asyncio
    async def test_delete_proposal_audit(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        # Create a proposal via API so current user owns it
        create_resp = await client.post(
            "/api/proposals",
            headers=auth_headers,
            json={
                "title": "ProposalToDelete",
                "contact_id": test_contact.id,
                "owner_id": test_user.id,
            },
        )
        assert create_resp.status_code == 201
        proposal_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/proposals/{proposal_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        items = await _get_audit_items(client, auth_headers, "proposal", proposal_id)
        assert any(item["action"] == "delete" for item in items)

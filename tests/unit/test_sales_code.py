"""
Unit tests for sales_code field on Leads and Contacts.

Tests create, update, and response inclusion for the sales_code field.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.contacts.models import Contact
from src.companies.models import Company


class TestLeadSalesCode:
    """Tests for sales_code field on leads."""

    @pytest.mark.asyncio
    async def test_create_lead_with_sales_code(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test creating a lead with a sales_code value."""
        response = await client.post(
            "/api/leads",
            headers=auth_headers,
            json={
                "first_name": "Sales",
                "last_name": "CodeLead",
                "email": "salescode@example.com",
                "status": "new",
                "sales_code": "SC-001",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["sales_code"] == "SC-001"

    @pytest.mark.asyncio
    async def test_create_lead_without_sales_code(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test creating a lead without sales_code defaults to null."""
        response = await client.post(
            "/api/leads",
            headers=auth_headers,
            json={
                "first_name": "No",
                "last_name": "SalesCode",
                "email": "nosalescode@example.com",
                "status": "new",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["sales_code"] is None

    @pytest.mark.asyncio
    async def test_update_lead_sales_code(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test updating a lead's sales_code."""
        lead_id = test_lead.id
        response = await client.patch(
            f"/api/leads/{lead_id}",
            headers=auth_headers,
            json={"sales_code": "SC-UPDATED"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sales_code"] == "SC-UPDATED"

    @pytest.mark.asyncio
    async def test_lead_sales_code_in_response(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test that sales_code appears in the lead GET response."""
        user_id = test_user.id
        # Create lead with sales_code
        lead = Lead(
            first_name="Response",
            last_name="Test",
            email="response_test@example.com",
            status="new",
            sales_code="SC-GET",
            owner_id=user_id,
            created_by_id=user_id,
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        response = await client.get(
            f"/api/leads/{lead.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sales_code"] == "SC-GET"


class TestContactSalesCode:
    """Tests for sales_code field on contacts."""

    @pytest.mark.asyncio
    async def test_create_contact_with_sales_code(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test creating a contact with a sales_code value."""
        response = await client.post(
            "/api/contacts",
            headers=auth_headers,
            json={
                "first_name": "Sales",
                "last_name": "CodeContact",
                "email": "salescode_contact@example.com",
                "status": "active",
                "sales_code": "SC-C001",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["sales_code"] == "SC-C001"

    @pytest.mark.asyncio
    async def test_create_contact_without_sales_code(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test creating a contact without sales_code defaults to null."""
        response = await client.post(
            "/api/contacts",
            headers=auth_headers,
            json={
                "first_name": "No",
                "last_name": "SalesCode",
                "email": "nosalescode_contact@example.com",
                "status": "active",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["sales_code"] is None

    @pytest.mark.asyncio
    async def test_update_contact_sales_code(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test updating a contact's sales_code."""
        contact_id = test_contact.id
        response = await client.patch(
            f"/api/contacts/{contact_id}",
            headers=auth_headers,
            json={"sales_code": "SC-C-UPDATED"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sales_code"] == "SC-C-UPDATED"

    @pytest.mark.asyncio
    async def test_contact_sales_code_in_response(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test that sales_code appears in the contact GET response."""
        user_id = test_user.id
        contact = Contact(
            first_name="Response",
            last_name="ContactTest",
            email="response_contact_test@example.com",
            status="active",
            sales_code="SC-C-GET",
            owner_id=user_id,
            created_by_id=user_id,
        )
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)

        response = await client.get(
            f"/api/contacts/{contact.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sales_code"] == "SC-C-GET"

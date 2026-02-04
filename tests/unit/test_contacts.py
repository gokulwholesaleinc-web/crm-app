"""
Unit tests for contacts CRUD endpoints.

Tests for list, create, get, update, and delete contact operations.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.contacts.models import Contact
from src.companies.models import Company


class TestContactsList:
    """Tests for contacts list endpoint with pagination."""

    @pytest.mark.asyncio
    async def test_list_contacts_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test listing contacts when none exist."""
        response = await client.get("/api/contacts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_contacts_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test listing contacts with existing data."""
        response = await client.get("/api/contacts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        assert any(c["id"] == test_contact.id for c in data["items"])

    @pytest.mark.asyncio
    async def test_list_contacts_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test contacts pagination."""
        # Create multiple contacts
        for i in range(15):
            contact = Contact(
                first_name=f"Contact{i}",
                last_name="Test",
                email=f"contact{i}@example.com",
                status="active",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(contact)
        await db_session.commit()

        # First page
        response = await client.get(
            "/api/contacts",
            headers=auth_headers,
            params={"page": 1, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert data["total"] == 15

        # Second page
        response = await client.get(
            "/api/contacts",
            headers=auth_headers,
            params={"page": 2, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["page"] == 2

    @pytest.mark.asyncio
    async def test_list_contacts_filter_by_company(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
        test_company: Company,
    ):
        """Test filtering contacts by company."""
        response = await client.get(
            "/api/contacts",
            headers=auth_headers,
            params={"company_id": test_company.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(c["company_id"] == test_company.id for c in data["items"])

    @pytest.mark.asyncio
    async def test_list_contacts_filter_by_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test filtering contacts by status."""
        response = await client.get(
            "/api/contacts",
            headers=auth_headers,
            params={"status": "active"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(c["status"] == "active" for c in data["items"])

    @pytest.mark.asyncio
    async def test_list_contacts_search(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test searching contacts."""
        response = await client.get(
            "/api/contacts",
            headers=auth_headers,
            params={"search": test_contact.first_name},
        )

        assert response.status_code == 200
        data = response.json()
        assert any(c["id"] == test_contact.id for c in data["items"])


class TestContactsCreate:
    """Tests for contact creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_contact_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test successful contact creation."""
        response = await client.post(
            "/api/contacts",
            headers=auth_headers,
            json={
                "first_name": "Alice",
                "last_name": "Johnson",
                "email": "alice.johnson@example.com",
                "phone": "+1-555-0150",
                "job_title": "Marketing Manager",
                "company_id": test_company.id,
                "status": "active",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "Alice"
        assert data["last_name"] == "Johnson"
        assert data["email"] == "alice.johnson@example.com"
        assert data["company_id"] == test_company.id
        assert "id" in data
        assert data["full_name"] == "Alice Johnson"

    @pytest.mark.asyncio
    async def test_create_contact_minimal(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating contact with minimal required fields."""
        response = await client.post(
            "/api/contacts",
            headers=auth_headers,
            json={
                "first_name": "Bob",
                "last_name": "Smith",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "Bob"
        assert data["last_name"] == "Smith"
        assert data["status"] == "active"  # Default

    @pytest.mark.asyncio
    async def test_create_contact_missing_first_name(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating contact without first_name fails."""
        response = await client.post(
            "/api/contacts",
            headers=auth_headers,
            json={
                "last_name": "Smith",
                "email": "noname@example.com",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_contact_missing_last_name(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating contact without last_name fails."""
        response = await client.post(
            "/api/contacts",
            headers=auth_headers,
            json={
                "first_name": "Bob",
                "email": "noname@example.com",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_contact_invalid_email(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating contact with invalid email fails."""
        response = await client.post(
            "/api/contacts",
            headers=auth_headers,
            json={
                "first_name": "Bob",
                "last_name": "Smith",
                "email": "not-an-email",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_contact_with_all_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
        test_user: User,
    ):
        """Test creating contact with all fields populated."""
        response = await client.post(
            "/api/contacts",
            headers=auth_headers,
            json={
                "first_name": "Complete",
                "last_name": "Contact",
                "email": "complete@example.com",
                "phone": "+1-555-0160",
                "mobile": "+1-555-0161",
                "job_title": "CTO",
                "department": "Technology",
                "company_id": test_company.id,
                "address_line1": "123 Main St",
                "address_line2": "Suite 100",
                "city": "New York",
                "state": "NY",
                "postal_code": "10001",
                "country": "USA",
                "linkedin_url": "https://linkedin.com/in/complete",
                "twitter_handle": "@complete",
                "description": "A complete contact record",
                "status": "active",
                "owner_id": test_user.id,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["department"] == "Technology"
        assert data["city"] == "New York"
        assert data["linkedin_url"] == "https://linkedin.com/in/complete"


class TestContactsGetById:
    """Tests for get contact by ID endpoint."""

    @pytest.mark.asyncio
    async def test_get_contact_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test getting contact by ID."""
        response = await client.get(
            f"/api/contacts/{test_contact.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_contact.id
        assert data["first_name"] == test_contact.first_name
        assert data["last_name"] == test_contact.last_name
        assert data["email"] == test_contact.email

    @pytest.mark.asyncio
    async def test_get_contact_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting non-existent contact."""
        response = await client.get(
            "/api/contacts/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_contact_includes_company(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
        test_company: Company,
    ):
        """Test that getting contact includes company info."""
        response = await client.get(
            f"/api/contacts/{test_contact.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["company"] is not None
        assert data["company"]["id"] == test_company.id
        assert data["company"]["name"] == test_company.name


class TestContactsUpdate:
    """Tests for contact update endpoint."""

    @pytest.mark.asyncio
    async def test_update_contact_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test updating contact."""
        response = await client.patch(
            f"/api/contacts/{test_contact.id}",
            headers=auth_headers,
            json={
                "first_name": "UpdatedFirstName",
                "job_title": "VP of Sales",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "UpdatedFirstName"
        assert data["job_title"] == "VP of Sales"
        # Other fields unchanged
        assert data["last_name"] == test_contact.last_name
        assert data["email"] == test_contact.email

    @pytest.mark.asyncio
    async def test_update_contact_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test updating non-existent contact."""
        response = await client.patch(
            "/api/contacts/99999",
            headers=auth_headers,
            json={"first_name": "Test"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_contact_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test updating contact status."""
        response = await client.patch(
            f"/api/contacts/{test_contact.id}",
            headers=auth_headers,
            json={"status": "inactive"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "inactive"

    @pytest.mark.asyncio
    async def test_update_contact_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test updating contact email."""
        response = await client.patch(
            f"/api/contacts/{test_contact.id}",
            headers=auth_headers,
            json={"email": "newemail@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newemail@example.com"

    @pytest.mark.asyncio
    async def test_update_contact_company(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
        test_user: User,
    ):
        """Test updating contact's company."""
        # Create a new company
        new_company = Company(
            name="New Company Inc",
            website="https://newcompany.com",
            status="prospect",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(new_company)
        await db_session.commit()
        await db_session.refresh(new_company)

        response = await client.patch(
            f"/api/contacts/{test_contact.id}",
            headers=auth_headers,
            json={"company_id": new_company.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["company_id"] == new_company.id


class TestContactsDelete:
    """Tests for contact delete endpoint."""

    @pytest.mark.asyncio
    async def test_delete_contact_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test deleting contact."""
        # Create a contact to delete
        contact = Contact(
            first_name="ToDelete",
            last_name="Contact",
            email="delete.me@example.com",
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)
        contact_id = contact.id

        response = await client.delete(
            f"/api/contacts/{contact_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify deletion
        result = await db_session.execute(
            select(Contact).where(Contact.id == contact_id)
        )
        deleted_contact = result.scalar_one_or_none()
        assert deleted_contact is None

    @pytest.mark.asyncio
    async def test_delete_contact_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test deleting non-existent contact."""
        response = await client.delete(
            "/api/contacts/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestContactsUnauthorized:
    """Tests for unauthorized access to contacts endpoints."""

    @pytest.mark.asyncio
    async def test_list_contacts_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test listing contacts without auth fails."""
        response = await client.get("/api/contacts")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_contact_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test creating contact without auth fails."""
        response = await client.post(
            "/api/contacts",
            json={"first_name": "Test", "last_name": "User"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_contact_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_contact: Contact
    ):
        """Test getting contact without auth fails."""
        response = await client.get(f"/api/contacts/{test_contact.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_contact_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_contact: Contact
    ):
        """Test updating contact without auth fails."""
        response = await client.patch(
            f"/api/contacts/{test_contact.id}",
            json={"first_name": "Hacked"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_contact_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_contact: Contact
    ):
        """Test deleting contact without auth fails."""
        response = await client.delete(f"/api/contacts/{test_contact.id}")
        assert response.status_code == 401

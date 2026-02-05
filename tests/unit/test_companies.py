"""
Unit tests for companies CRUD endpoints.

Tests for list, create, get, update, and delete company operations.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.companies.models import Company
from src.contacts.models import Contact


class TestCompaniesList:
    """Tests for companies list endpoint with pagination."""

    @pytest.mark.asyncio
    async def test_list_companies_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test listing companies when none exist."""
        response = await client.get("/api/companies", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_companies_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test listing companies with existing data."""
        response = await client.get("/api/companies", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        assert any(c["id"] == test_company.id for c in data["items"])

    @pytest.mark.asyncio
    async def test_list_companies_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test companies pagination."""
        # Create multiple companies
        for i in range(15):
            company = Company(
                name=f"Company {i}",
                website=f"https://company{i}.com",
                status="prospect",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(company)
        await db_session.commit()

        # First page
        response = await client.get(
            "/api/companies",
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
            "/api/companies",
            headers=auth_headers,
            params={"page": 2, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["page"] == 2

    @pytest.mark.asyncio
    async def test_list_companies_filter_by_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test filtering companies by status."""
        response = await client.get(
            "/api/companies",
            headers=auth_headers,
            params={"status": "prospect"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(c["status"] == "prospect" for c in data["items"])

    @pytest.mark.asyncio
    async def test_list_companies_filter_by_industry(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test filtering companies by industry."""
        response = await client.get(
            "/api/companies",
            headers=auth_headers,
            params={"industry": "Technology"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(c["industry"] == "Technology" for c in data["items"])

    @pytest.mark.asyncio
    async def test_list_companies_search(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test searching companies."""
        response = await client.get(
            "/api/companies",
            headers=auth_headers,
            params={"search": test_company.name},
        )

        assert response.status_code == 200
        data = response.json()
        assert any(c["id"] == test_company.id for c in data["items"])


class TestCompaniesCreate:
    """Tests for company creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_company_success(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test successful company creation."""
        response = await client.post(
            "/api/companies",
            headers=auth_headers,
            json={
                "name": "Acme Corporation",
                "website": "https://acme.com",
                "industry": "Manufacturing",
                "phone": "+1-555-0200",
                "email": "info@acme.com",
                "city": "Los Angeles",
                "state": "CA",
                "country": "USA",
                "status": "prospect",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Acme Corporation"
        assert data["industry"] == "Manufacturing"
        assert data["website"] == "https://acme.com"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_company_minimal(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating company with minimal required fields."""
        response = await client.post(
            "/api/companies",
            headers=auth_headers,
            json={
                "name": "Minimal Company",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Company"
        assert data["status"] == "prospect"  # Default

    @pytest.mark.asyncio
    async def test_create_company_missing_name(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating company without name fails."""
        response = await client.post(
            "/api/companies",
            headers=auth_headers,
            json={
                "website": "https://noname.com",
                "industry": "Technology",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_company_with_all_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test creating company with all fields populated."""
        response = await client.post(
            "/api/companies",
            headers=auth_headers,
            json={
                "name": "Complete Company Ltd",
                "website": "https://complete.com",
                "industry": "Finance",
                "company_size": "mid-market",
                "phone": "+1-555-0300",
                "email": "contact@complete.com",
                "address_line1": "100 Finance Way",
                "address_line2": "Floor 20",
                "city": "New York",
                "state": "NY",
                "postal_code": "10001",
                "country": "USA",
                "annual_revenue": 50000000.0,
                "employee_count": 500,
                "linkedin_url": "https://linkedin.com/company/complete",
                "twitter_handle": "@complete",
                "description": "A complete financial services company",
                "status": "customer",
                "owner_id": test_user.id,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["company_size"] == "mid-market"
        assert data["annual_revenue"] == 50000000.0
        assert data["employee_count"] == 500
        assert data["status"] == "customer"


class TestCompaniesGetById:
    """Tests for get company by ID endpoint."""

    @pytest.mark.asyncio
    async def test_get_company_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test getting company by ID."""
        response = await client.get(
            f"/api/companies/{test_company.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_company.id
        assert data["name"] == test_company.name
        assert data["website"] == test_company.website

    @pytest.mark.asyncio
    async def test_get_company_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting non-existent company."""
        response = await client.get(
            "/api/companies/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_company_includes_contact_count(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
        test_contact: Contact,
    ):
        """Test that getting company includes contact count."""
        response = await client.get(
            f"/api/companies/{test_company.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "contact_count" in data
        assert data["contact_count"] >= 1  # At least our test_contact


class TestCompaniesUpdate:
    """Tests for company update endpoint."""

    @pytest.mark.asyncio
    async def test_update_company_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test updating company."""
        response = await client.patch(
            f"/api/companies/{test_company.id}",
            headers=auth_headers,
            json={
                "name": "Updated Company Name",
                "industry": "Healthcare",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Company Name"
        assert data["industry"] == "Healthcare"
        # Other fields unchanged
        assert data["website"] == test_company.website

    @pytest.mark.asyncio
    async def test_update_company_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test updating non-existent company."""
        response = await client.patch(
            "/api/companies/99999",
            headers=auth_headers,
            json={"name": "Test"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_company_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test updating company status."""
        response = await client.patch(
            f"/api/companies/{test_company.id}",
            headers=auth_headers,
            json={"status": "customer"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "customer"

    @pytest.mark.asyncio
    async def test_update_company_contact_info(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test updating company contact information."""
        response = await client.patch(
            f"/api/companies/{test_company.id}",
            headers=auth_headers,
            json={
                "phone": "+1-555-9999",
                "email": "updated@company.com",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["phone"] == "+1-555-9999"
        assert data["email"] == "updated@company.com"

    @pytest.mark.asyncio
    async def test_update_company_address(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test updating company address."""
        response = await client.patch(
            f"/api/companies/{test_company.id}",
            headers=auth_headers,
            json={
                "address_line1": "200 New Street",
                "city": "Seattle",
                "state": "WA",
                "country": "USA",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["city"] == "Seattle"
        assert data["state"] == "WA"

    @pytest.mark.asyncio
    async def test_update_company_financial_info(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test updating company financial information."""
        response = await client.patch(
            f"/api/companies/{test_company.id}",
            headers=auth_headers,
            json={
                "annual_revenue": 10000000.0,
                "employee_count": 200,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["annual_revenue"] == 10000000.0
        assert data["employee_count"] == 200


class TestCompaniesDelete:
    """Tests for company delete endpoint."""

    @pytest.mark.asyncio
    async def test_delete_company_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test deleting company."""
        # Create a company to delete (without contacts)
        company = Company(
            name="To Delete Company",
            website="https://deleteme.com",
            status="prospect",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(company)
        await db_session.commit()
        await db_session.refresh(company)
        company_id = company.id

        response = await client.delete(
            f"/api/companies/{company_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify deletion
        result = await db_session.execute(
            select(Company).where(Company.id == company_id)
        )
        deleted_company = result.scalar_one_or_none()
        assert deleted_company is None

    @pytest.mark.asyncio
    async def test_delete_company_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test deleting non-existent company."""
        response = await client.delete(
            "/api/companies/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestCompaniesUnauthorized:
    """Tests for unauthorized access to companies endpoints."""

    @pytest.mark.asyncio
    async def test_list_companies_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test listing companies without auth fails."""
        response = await client.get("/api/companies")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_company_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test creating company without auth fails."""
        response = await client.post(
            "/api/companies",
            json={"name": "Test Company"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_company_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_company: Company
    ):
        """Test getting company without auth fails."""
        response = await client.get(f"/api/companies/{test_company.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_company_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_company: Company
    ):
        """Test updating company without auth fails."""
        response = await client.patch(
            f"/api/companies/{test_company.id}",
            json={"name": "Hacked"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_company_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_company: Company
    ):
        """Test deleting company without auth fails."""
        response = await client.delete(f"/api/companies/{test_company.id}")
        assert response.status_code == 401

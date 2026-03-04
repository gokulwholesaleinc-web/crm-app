"""
Unit tests for import/export functionality.

Tests for CSV export, import, and template generation.

Note: TestBulkAssign and TestBulkUpdate were removed from this file
during consolidation. The more comprehensive versions (with batch
operations and DB verification) live in test_bulk_operations.py.
Unique tests from this file (contacts assign, updates_applied assertion)
were merged into test_bulk_operations.py.
"""

import pytest
import csv
import io
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.auth.security import get_password_hash
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead, LeadSource


class TestExportContacts:
    """Tests for contacts export endpoint."""

    @pytest.mark.asyncio
    async def test_export_contacts_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test exporting contacts when none exist."""
        response = await client.get(
            "/api/import-export/export/contacts",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        assert "contacts_export.csv" in response.headers["content-disposition"]

        # Should have header row only
        content = response.text
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) >= 1  # At least header

    @pytest.mark.asyncio
    async def test_export_contacts_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test exporting contacts with existing data."""
        response = await client.get(
            "/api/import-export/export/contacts",
            headers=auth_headers,
        )

        assert response.status_code == 200
        content = response.text

        # Parse CSV
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) >= 1

        # Check that test contact is in export
        contact_emails = [row.get("email", "") for row in rows]
        assert test_contact.email in contact_emails

    @pytest.mark.asyncio
    async def test_export_contacts_csv_structure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test exported contacts CSV has correct structure."""
        response = await client.get(
            "/api/import-export/export/contacts",
            headers=auth_headers,
        )

        assert response.status_code == 200
        content = response.text

        reader = csv.DictReader(io.StringIO(content))
        fieldnames = reader.fieldnames

        # Check required fields are present
        expected_fields = [
            "first_name", "last_name", "email", "phone",
            "job_title", "status"
        ]
        for field in expected_fields:
            assert field in fieldnames


class TestExportCompanies:
    """Tests for companies export endpoint."""

    @pytest.mark.asyncio
    async def test_export_companies_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test exporting companies when none exist."""
        response = await client.get(
            "/api/import-export/export/companies",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "companies_export.csv" in response.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_export_companies_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test exporting companies with existing data."""
        response = await client.get(
            "/api/import-export/export/companies",
            headers=auth_headers,
        )

        assert response.status_code == 200
        content = response.text

        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) >= 1

        company_names = [row.get("name", "") for row in rows]
        assert test_company.name in company_names

    @pytest.mark.asyncio
    async def test_export_companies_csv_structure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test exported companies CSV has correct structure."""
        response = await client.get(
            "/api/import-export/export/companies",
            headers=auth_headers,
        )

        assert response.status_code == 200
        content = response.text

        reader = csv.DictReader(io.StringIO(content))
        fieldnames = reader.fieldnames

        expected_fields = ["name", "website", "industry", "phone", "email", "status"]
        for field in expected_fields:
            assert field in fieldnames


class TestExportLeads:
    """Tests for leads export endpoint."""

    @pytest.mark.asyncio
    async def test_export_leads_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test exporting leads when none exist."""
        response = await client.get(
            "/api/import-export/export/leads",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "leads_export.csv" in response.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_export_leads_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test exporting leads with existing data."""
        response = await client.get(
            "/api/import-export/export/leads",
            headers=auth_headers,
        )

        assert response.status_code == 200
        content = response.text

        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) >= 1

        lead_emails = [row.get("email", "") for row in rows]
        assert test_lead.email in lead_emails


class TestImportContacts:
    """Tests for contacts import endpoint."""

    @pytest.mark.asyncio
    async def test_import_contacts_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test successful contacts import."""
        csv_content = """first_name,last_name,email,phone,status
Import1,Test,import1@test.com,+1-555-0001,active
Import2,Test,import2@test.com,+1-555-0002,active
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["imported"] == 2
        assert len(data["errors"]) == 0

    @pytest.mark.asyncio
    async def test_import_contacts_with_errors(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test contacts import with some invalid rows."""
        csv_content = """first_name,last_name,email,phone,status
Valid,Contact,valid@test.com,+1-555-0001,active
,MissingFirst,nofirst@test.com,+1-555-0002,active
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/contacts",
            headers=auth_headers,
            files=files,
            params={"skip_errors": True},
        )

        assert response.status_code == 200
        data = response.json()
        # At least one should be imported
        assert data["imported"] >= 1

    @pytest.mark.asyncio
    async def test_import_contacts_invalid_file_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test contacts import with non-CSV file."""
        files = {"file": ("contacts.txt", "not csv content", "text/plain")}

        response = await client.post(
            "/api/import-export/import/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 400
        assert "CSV" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_import_contacts_empty_file(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test contacts import with empty CSV file."""
        csv_content = "first_name,last_name,email,phone,status\n"
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 0


class TestImportCompanies:
    """Tests for companies import endpoint."""

    @pytest.mark.asyncio
    async def test_import_companies_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test successful companies import."""
        csv_content = """name,website,industry,phone,status
Import Corp 1,https://import1.com,Technology,+1-555-0001,prospect
Import Corp 2,https://import2.com,Finance,+1-555-0002,customer
"""
        files = {"file": ("companies.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/companies",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["imported"] == 2

    @pytest.mark.asyncio
    async def test_import_companies_invalid_file_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test companies import with non-CSV file."""
        files = {"file": ("companies.xlsx", "excel content", "application/vnd.ms-excel")}

        response = await client.post(
            "/api/import-export/import/companies",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 400


class TestImportLeads:
    """Tests for leads import endpoint."""

    @pytest.mark.asyncio
    async def test_import_leads_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test successful leads import."""
        csv_content = """first_name,last_name,email,phone,company_name,status
Lead1,Import,lead1@test.com,+1-555-0001,Acme Inc,new
Lead2,Import,lead2@test.com,+1-555-0002,Big Corp,contacted
"""
        files = {"file": ("leads.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/leads",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["imported"] == 2

    @pytest.mark.asyncio
    async def test_import_leads_with_budget(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test leads import with budget information."""
        csv_content = """first_name,last_name,email,budget_amount,budget_currency,status
Budget,Lead,budget@test.com,50000,USD,new
"""
        files = {"file": ("leads.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/leads",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1

    @pytest.mark.asyncio
    async def test_import_leads_invalid_file_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test leads import with non-CSV file."""
        files = {"file": ("leads.json", '{"leads": []}', "application/json")}

        response = await client.post(
            "/api/import-export/import/leads",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 400


class TestImportTemplates:
    """Tests for import template endpoints."""

    @pytest.mark.asyncio
    async def test_get_contacts_template(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting contacts import template."""
        response = await client.get(
            "/api/import-export/template/contacts",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "contacts_template.csv" in response.headers["content-disposition"]

        # Template should have headers but no data
        content = response.text
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 1  # Header only

        # Check expected fields
        headers = rows[0]
        assert "first_name" in headers
        assert "last_name" in headers
        assert "email" in headers

    @pytest.mark.asyncio
    async def test_get_companies_template(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting companies import template."""
        response = await client.get(
            "/api/import-export/template/companies",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "companies_template.csv" in response.headers["content-disposition"]

        content = response.text
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 1

        headers = rows[0]
        assert "name" in headers
        assert "website" in headers
        assert "industry" in headers

    @pytest.mark.asyncio
    async def test_get_leads_template(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting leads import template."""
        response = await client.get(
            "/api/import-export/template/leads",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "leads_template.csv" in response.headers["content-disposition"]

        content = response.text
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 1

        headers = rows[0]
        assert "first_name" in headers
        assert "last_name" in headers
        assert "company_name" in headers

    @pytest.mark.asyncio
    async def test_get_template_invalid_type(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting template for invalid entity type."""
        response = await client.get(
            "/api/import-export/template/invalid",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Invalid entity type" in response.json()["detail"]


class TestImportExportRoundTrip:
    """Tests for import/export round-trip consistency."""

    @pytest.mark.asyncio
    async def test_contacts_roundtrip(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test contacts can be exported and re-imported."""
        # Create contacts
        for i in range(3):
            contact = Contact(
                first_name=f"Roundtrip{i}",
                last_name="Contact",
                email=f"roundtrip{i}@test.com",
                phone=f"+1-555-100{i}",
                status="active",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(contact)
        await db_session.commit()

        # Export
        export_response = await client.get(
            "/api/import-export/export/contacts",
            headers=auth_headers,
        )
        assert export_response.status_code == 200
        csv_content = export_response.text

        # Verify export contains our contacts
        reader = csv.DictReader(io.StringIO(csv_content))
        exported_emails = [row["email"] for row in reader]
        assert "roundtrip0@test.com" in exported_emails

    @pytest.mark.asyncio
    async def test_companies_roundtrip(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test companies can be exported and re-imported."""
        # Create companies
        for i in range(2):
            company = Company(
                name=f"Roundtrip Corp {i}",
                website=f"https://roundtrip{i}.com",
                industry="Technology",
                status="prospect",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(company)
        await db_session.commit()

        # Export
        export_response = await client.get(
            "/api/import-export/export/companies",
            headers=auth_headers,
        )
        assert export_response.status_code == 200


class TestExportDataScoping:
    """Tests that export respects role-based data scoping."""

    @pytest.mark.asyncio
    async def test_admin_exports_all_contacts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        admin_auth_headers: dict,
    ):
        """Admin user exports contacts owned by other users."""
        # Create a separate user to own some contacts
        other_user = User(
            email="otheruser_contacts@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Other User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(other_user)
        await db_session.flush()

        # Create contacts owned by the other user (not the admin)
        for i in range(3):
            contact = Contact(
                first_name=f"OtherOwner{i}",
                last_name="Contact",
                email=f"otherowner_contact{i}@test.com",
                status="active",
                owner_id=other_user.id,
                created_by_id=other_user.id,
            )
            db_session.add(contact)
        await db_session.commit()

        # Admin exports - should see all contacts including other user's
        response = await client.get(
            "/api/import-export/export/contacts",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        reader = csv.DictReader(io.StringIO(response.text))
        rows = list(reader)
        exported_emails = [row["email"] for row in rows]

        assert len(rows) >= 3
        assert "otherowner_contact0@test.com" in exported_emails
        assert "otherowner_contact1@test.com" in exported_emails
        assert "otherowner_contact2@test.com" in exported_emails

    @pytest.mark.asyncio
    async def test_admin_exports_all_companies(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        admin_auth_headers: dict,
    ):
        """Admin user exports companies owned by other users."""
        other_user = User(
            email="otheruser_companies@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Other User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(other_user)
        await db_session.flush()

        for i in range(2):
            company = Company(
                name=f"OtherOwner Corp {i}",
                status="prospect",
                owner_id=other_user.id,
                created_by_id=other_user.id,
            )
            db_session.add(company)
        await db_session.commit()

        response = await client.get(
            "/api/import-export/export/companies",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        reader = csv.DictReader(io.StringIO(response.text))
        rows = list(reader)
        company_names = [row["name"] for row in rows]

        assert len(rows) >= 2
        assert "OtherOwner Corp 0" in company_names
        assert "OtherOwner Corp 1" in company_names

    @pytest.mark.asyncio
    async def test_admin_exports_all_leads(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_admin_user: User,
        admin_auth_headers: dict,
    ):
        """Admin user exports leads owned by other users."""
        other_user = User(
            email="otheruser_leads@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Other User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(other_user)
        await db_session.flush()

        for i in range(2):
            lead = Lead(
                first_name=f"OtherOwner{i}",
                last_name="Lead",
                email=f"otherowner_lead{i}@test.com",
                status="new",
                owner_id=other_user.id,
                created_by_id=other_user.id,
            )
            db_session.add(lead)
        await db_session.commit()

        response = await client.get(
            "/api/import-export/export/leads",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        reader = csv.DictReader(io.StringIO(response.text))
        rows = list(reader)
        lead_emails = [row["email"] for row in rows]

        assert len(rows) >= 2
        assert "otherowner_lead0@test.com" in lead_emails
        assert "otherowner_lead1@test.com" in lead_emails

    @pytest.mark.asyncio
    async def test_sales_rep_exports_only_own_contacts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        _sales_rep_user: User,
        sales_rep_auth_headers: dict,
    ):
        """Sales rep user exports only contacts they own."""
        # Create a contact owned by the sales rep
        own_contact = Contact(
            first_name="OwnContact",
            last_name="Rep",
            email="own_contact@test.com",
            status="active",
            owner_id=_sales_rep_user.id,
            created_by_id=_sales_rep_user.id,
        )
        db_session.add(own_contact)

        # Create a contact owned by someone else
        other_user = User(
            email="anotheruser_scope@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Another User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(other_user)
        await db_session.flush()

        other_contact = Contact(
            first_name="OtherContact",
            last_name="User",
            email="other_contact_scoped@test.com",
            status="active",
            owner_id=other_user.id,
            created_by_id=other_user.id,
        )
        db_session.add(other_contact)
        await db_session.commit()

        response = await client.get(
            "/api/import-export/export/contacts",
            headers=sales_rep_auth_headers,
        )
        assert response.status_code == 200
        reader = csv.DictReader(io.StringIO(response.text))
        rows = list(reader)
        exported_emails = [row["email"] for row in rows]

        # Sales rep should see their own contact
        assert "own_contact@test.com" in exported_emails
        # Sales rep should NOT see the other user's contact
        assert "other_contact_scoped@test.com" not in exported_emails


class TestImportExportUnauthorized:
    """Tests for unauthorized access to import/export endpoints."""

    @pytest.mark.asyncio
    async def test_export_contacts_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test export contacts without auth fails."""
        response = await client.get("/api/import-export/export/contacts")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_export_companies_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test export companies without auth fails."""
        response = await client.get("/api/import-export/export/companies")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_export_leads_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test export leads without auth fails."""
        response = await client.get("/api/import-export/export/leads")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_import_contacts_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test import contacts without auth fails."""
        files = {"file": ("contacts.csv", "first_name,last_name\n", "text/csv")}
        response = await client.post(
            "/api/import-export/import/contacts",
            files=files,
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_template_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test get template without auth fails."""
        response = await client.get("/api/import-export/template/contacts")
        assert response.status_code == 401

"""
Unit tests for import/export functionality.

Tests for CSV export, import, template generation, smart column mapping,
duplicate detection, and preview.
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
from src.import_export.csv_handler import _map_columns, _normalize_header


class TestExportContacts:
    """Tests for contacts export endpoint."""

    @pytest.mark.asyncio
    async def test_export_contacts_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        response = await client.get(
            "/api/import-export/export/contacts",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        assert "contacts_export.csv" in response.headers["content-disposition"]

        content = response.text
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) >= 1

    @pytest.mark.asyncio
    async def test_export_contacts_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        response = await client.get(
            "/api/import-export/export/contacts",
            headers=auth_headers,
        )

        assert response.status_code == 200
        content = response.text

        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) >= 1

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
        response = await client.get(
            "/api/import-export/export/contacts",
            headers=auth_headers,
        )

        assert response.status_code == 200
        content = response.text

        reader = csv.DictReader(io.StringIO(content))
        fieldnames = reader.fieldnames

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
        assert data["imported_count"] == 2
        assert len(data["errors"]) == 0
        assert data["duplicates_skipped"] == 0

    @pytest.mark.asyncio
    async def test_import_contacts_with_errors(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
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
        assert data["imported_count"] >= 1

    @pytest.mark.asyncio
    async def test_import_contacts_invalid_file_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
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
        csv_content = "first_name,last_name,email,phone,status\n"
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["imported_count"] == 0

    @pytest.mark.asyncio
    async def test_import_contacts_duplicate_detection(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Duplicate emails should be skipped during import."""
        # First import
        csv_content = """first_name,last_name,email,phone,status
Dup1,Test,dup@test.com,+1-555-0001,active
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}
        response = await client.post(
            "/api/import-export/import/contacts",
            headers=auth_headers,
            files=files,
        )
        assert response.status_code == 200
        assert response.json()["imported_count"] == 1

        # Second import with same email
        csv_content2 = """first_name,last_name,email,phone,status
Dup2,Test,dup@test.com,+1-555-0002,active
New,Contact,new@test.com,+1-555-0003,active
"""
        files2 = {"file": ("contacts.csv", csv_content2, "text/csv")}
        response2 = await client.post(
            "/api/import-export/import/contacts",
            headers=auth_headers,
            files=files2,
        )
        assert response2.status_code == 200
        data = response2.json()
        assert data["imported_count"] == 1
        assert data["duplicates_skipped"] == 1

    @pytest.mark.asyncio
    async def test_import_contacts_smart_column_mapping(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """CSV with non-standard headers like 'First Name' should be auto-mapped."""
        csv_content = """First Name,Last Name,Email Address,Phone Number,Status
Smart1,Map,smart1@test.com,+1-555-0010,active
Smart2,Map,smart2@test.com,+1-555-0011,active
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["imported_count"] == 2

        # Verify data was mapped correctly
        result = await db_session.execute(
            select(Contact).where(Contact.email == "smart1@test.com")
        )
        contact = result.scalar_one_or_none()
        assert contact is not None
        assert contact.first_name == "Smart1"
        assert contact.last_name == "Map"


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
        assert data["imported_count"] == 2

    @pytest.mark.asyncio
    async def test_import_companies_invalid_file_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        files = {"file": ("companies.xlsx", "excel content", "application/vnd.ms-excel")}

        response = await client.post(
            "/api/import-export/import/companies",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_import_companies_duplicate_email_detection(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Companies with duplicate emails should be skipped."""
        csv_content = """name,email,industry,status
Corp A,corp@test.com,Tech,prospect
"""
        files = {"file": ("companies.csv", csv_content, "text/csv")}
        await client.post("/api/import-export/import/companies", headers=auth_headers, files=files)

        csv_content2 = """name,email,industry,status
Corp B,corp@test.com,Finance,customer
Corp C,newcorp@test.com,Retail,prospect
"""
        files2 = {"file": ("companies.csv", csv_content2, "text/csv")}
        response = await client.post("/api/import-export/import/companies", headers=auth_headers, files=files2)
        data = response.json()
        assert data["imported_count"] == 1
        assert data["duplicates_skipped"] == 1


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
        assert data["imported_count"] == 2

    @pytest.mark.asyncio
    async def test_import_leads_with_budget(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
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
        assert data["imported_count"] == 1

    @pytest.mark.asyncio
    async def test_import_leads_invalid_file_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
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
        response = await client.get(
            "/api/import-export/template/contacts",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "contacts_template.csv" in response.headers["content-disposition"]

        content = response.text
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        assert len(rows) == 1

        headers = rows[0]
        assert "first_name" in headers
        assert "last_name" in headers
        assert "email" in headers

    @pytest.mark.asyncio
    async def test_get_companies_template(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
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
        response = await client.get(
            "/api/import-export/template/invalid",
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "Invalid entity type" in response.json()["detail"]


class TestImportPreview:
    """Tests for the CSV preview endpoint."""

    @pytest.mark.asyncio
    async def test_preview_contacts_standard_headers(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        csv_content = """first_name,last_name,email,phone,status
John,Doe,john@test.com,+1-555-0001,active
Jane,Smith,jane@test.com,+1-555-0002,active
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/preview/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_rows"] == 2
        assert len(data["preview_rows"]) == 2
        assert data["column_mapping"]["first_name"] == "first_name"
        assert data["column_mapping"]["email"] == "email"

    @pytest.mark.asyncio
    async def test_preview_contacts_aliased_headers(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Headers like 'First Name', 'Email Address' should be auto-mapped."""
        csv_content = """First Name,Last Name,Email Address,Telephone
John,Doe,john@test.com,+1-555-0001
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/preview/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        mapping = data["column_mapping"]
        assert mapping["First Name"] == "first_name"
        assert mapping["Last Name"] == "last_name"
        assert mapping["Email Address"] == "email"
        assert mapping["Telephone"] == "phone"

    @pytest.mark.asyncio
    async def test_preview_shows_unmapped_columns(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        csv_content = """first_name,last_name,email,random_column
John,Doe,john@test.com,whatever
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/preview/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert "random_column" in data["unmapped_columns"]

    @pytest.mark.asyncio
    async def test_preview_detects_duplicate_emails(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        csv_content = """first_name,last_name,email
John,Doe,dup@test.com
Jane,Smith,dup@test.com
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/preview/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["warnings"]) >= 1
        assert "duplicate email" in data["warnings"][0].lower()

    @pytest.mark.asyncio
    async def test_preview_invalid_entity_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        files = {"file": ("data.csv", "col1,col2\na,b\n", "text/csv")}
        response = await client.post(
            "/api/import-export/preview/invalid",
            headers=auth_headers,
            files=files,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_preview_limits_to_5_rows(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        rows = ["first_name,last_name,email"]
        for i in range(20):
            rows.append(f"Name{i},Last{i},name{i}@test.com")
        csv_content = "\n".join(rows) + "\n"
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/preview/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_rows"] == 20
        assert len(data["preview_rows"]) == 5


class TestColumnMapping:
    """Unit tests for the column mapping logic (no DB needed)."""

    def test_exact_match(self):
        mapping = _map_columns(["first_name", "last_name", "email"], ["first_name", "last_name", "email", "phone"])
        assert mapping == {"first_name": "first_name", "last_name": "last_name", "email": "email"}

    def test_alias_match(self):
        mapping = _map_columns(["First Name", "Surname", "Email Address"], ["first_name", "last_name", "email", "phone"])
        assert mapping["First Name"] == "first_name"
        assert mapping["Surname"] == "last_name"
        assert mapping["Email Address"] == "email"

    def test_fuzzy_match(self):
        mapping = _map_columns(["first_name", "last_name", "email_addr"], ["first_name", "last_name", "email", "phone"])
        assert mapping.get("first_name") == "first_name"
        assert mapping.get("last_name") == "last_name"

    def test_no_match_for_garbage(self):
        mapping = _map_columns(["xyzabc123"], ["first_name", "email"])
        assert "xyzabc123" not in mapping

    def test_normalize_header(self):
        assert _normalize_header("First Name") == "firstname"
        assert _normalize_header("  Email Address  ") == "emailaddress"
        assert _normalize_header("phone_number") == "phonenumber"


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

        export_response = await client.get(
            "/api/import-export/export/contacts",
            headers=auth_headers,
        )
        assert export_response.status_code == 200
        csv_content = export_response.text

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
        other_user = User(
            email="otheruser_contacts@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Other User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(other_user)
        await db_session.flush()

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
        own_contact = Contact(
            first_name="OwnContact",
            last_name="Rep",
            email="own_contact@test.com",
            status="active",
            owner_id=_sales_rep_user.id,
            created_by_id=_sales_rep_user.id,
        )
        db_session.add(own_contact)

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

        assert "own_contact@test.com" in exported_emails
        assert "other_contact_scoped@test.com" not in exported_emails


class TestImportExportUnauthorized:
    """Tests for unauthorized access to import/export endpoints."""

    @pytest.mark.asyncio
    async def test_export_contacts_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.get("/api/import-export/export/contacts")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_export_companies_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.get("/api/import-export/export/companies")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_export_leads_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.get("/api/import-export/export/leads")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_import_contacts_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
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
        response = await client.get("/api/import-export/template/contacts")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_preview_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        files = {"file": ("contacts.csv", "first_name,last_name\n", "text/csv")}
        response = await client.post(
            "/api/import-export/preview/contacts",
            files=files,
        )
        assert response.status_code == 401

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
from src.import_export.csv_handler import _map_columns, _normalize_header, _split_full_name, _find_name_column


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


class TestMondayComImport:
    """Tests for Monday.com CSV import compatibility."""

    @pytest.mark.asyncio
    async def test_import_contacts_with_name_column(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Monday.com exports a single 'Name' column — should split into first_name + last_name."""
        csv_content = """Name,Email,Phone,Status
John Smith,john.monday@test.com,+1-555-0001,active
Jane Doe,jane.monday@test.com,+1-555-0002,active
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

        result = await db_session.execute(
            select(Contact).where(Contact.email == "john.monday@test.com")
        )
        contact = result.scalar_one_or_none()
        assert contact is not None
        assert contact.first_name == "John"
        assert contact.last_name == "Smith"

    @pytest.mark.asyncio
    async def test_import_contacts_with_person_column(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Monday.com 'Person' column should also split into first_name + last_name."""
        csv_content = """Person,Email,Phone
Alice Johnson,alice.monday@test.com,+1-555-0010
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        assert response.json()["imported_count"] == 1

        result = await db_session.execute(
            select(Contact).where(Contact.email == "alice.monday@test.com")
        )
        contact = result.scalar_one_or_none()
        assert contact is not None
        assert contact.first_name == "Alice"
        assert contact.last_name == "Johnson"

    @pytest.mark.asyncio
    async def test_import_leads_with_monday_headers(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Monday.com lead export with Lead Status, Name, and Company columns."""
        csv_content = """Name,Email,Phone,Company,Lead Status
Bob Wilson,bob.monday@test.com,+1-555-0020,Acme Inc,new
"""
        files = {"file": ("leads.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/leads",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        assert response.json()["imported_count"] == 1

        result = await db_session.execute(
            select(Lead).where(Lead.email == "bob.monday@test.com")
        )
        lead = result.scalar_one_or_none()
        assert lead is not None
        assert lead.first_name == "Bob"
        assert lead.last_name == "Wilson"
        assert lead.company_name == "Acme Inc"
        assert lead.status == "new"

    @pytest.mark.asyncio
    async def test_import_contacts_single_name_no_last(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Single-word name should set first_name only, last_name empty."""
        csv_content = """Name,Email
Madonna,madonna.monday@test.com
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        assert response.json()["imported_count"] == 1

        result = await db_session.execute(
            select(Contact).where(Contact.email == "madonna.monday@test.com")
        )
        contact = result.scalar_one_or_none()
        assert contact is not None
        assert contact.first_name == "Madonna"
        assert contact.last_name == ""

    @pytest.mark.asyncio
    async def test_name_column_ignored_when_first_last_present(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """If CSV has both first_name/last_name AND Name, use first_name/last_name."""
        csv_content = """first_name,last_name,Name,Email
Explicit,Fields,Should Ignore,explicit.monday@test.com
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        assert response.json()["imported_count"] == 1

        result = await db_session.execute(
            select(Contact).where(Contact.email == "explicit.monday@test.com")
        )
        contact = result.scalar_one_or_none()
        assert contact is not None
        assert contact.first_name == "Explicit"
        assert contact.last_name == "Fields"

    @pytest.mark.asyncio
    async def test_monday_unmapped_columns_ignored(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Monday.com metadata columns (Subitems, Board, Item ID) should be ignored."""
        csv_content = """Name,Email,Subitems,Board,Item ID,Creation Log
Test User,monday.meta@test.com,sub1,My Board,12345,2024-01-01
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        assert response.json()["imported_count"] == 1

    @pytest.mark.asyncio
    async def test_preview_monday_csv_contacts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Preview should show name split and not list Name as unmapped."""
        csv_content = """Name,Email,Phone,Status
John Smith,john@preview.com,+1-555-0001,active
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/preview/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert "Name" not in data["unmapped_columns"]
        assert data["preview_rows"][0]["first_name"] == "John"
        assert data["preview_rows"][0]["last_name"] == "Smith"
        assert "first_name" not in data["missing_fields"]
        assert "last_name" not in data["missing_fields"]

    @pytest.mark.asyncio
    async def test_monday_location_maps_to_address(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Monday.com 'Location' column should map to address_line1."""
        csv_content = """first_name,last_name,email,Location
Loc,Test,loc.monday@test.com,123 Main St
"""
        files = {"file": ("contacts.csv", csv_content, "text/csv")}

        response = await client.post(
            "/api/import-export/import/contacts",
            headers=auth_headers,
            files=files,
        )

        assert response.status_code == 200
        assert response.json()["imported_count"] == 1

        result = await db_session.execute(
            select(Contact).where(Contact.email == "loc.monday@test.com")
        )
        contact = result.scalar_one_or_none()
        assert contact is not None
        assert contact.address_line1 == "123 Main St"


class TestSplitFullName:
    """Unit tests for _split_full_name helper."""

    def test_two_word_name(self):
        assert _split_full_name("John Smith") == ("John", "Smith")

    def test_single_word_name(self):
        assert _split_full_name("Madonna") == ("Madonna", "")

    def test_three_word_name(self):
        first, last = _split_full_name("John Paul Smith")
        assert first == "John"
        assert last == "Paul Smith"

    def test_empty_string(self):
        assert _split_full_name("") == ("", "")

    def test_whitespace_only(self):
        assert _split_full_name("   ") == ("", "")

    def test_extra_whitespace(self):
        assert _split_full_name("  John   Smith  ") == ("John", "Smith")


class TestFindNameColumn:
    """Unit tests for _find_name_column helper."""

    def test_finds_name_column(self):
        headers = ["Name", "Email", "Phone"]
        mapping = {"Email": "email", "Phone": "phone"}
        fields = ["first_name", "last_name", "email", "phone"]
        assert _find_name_column(headers, mapping, fields) == "Name"

    def test_finds_person_column(self):
        headers = ["Person", "Email"]
        mapping = {"Email": "email"}
        fields = ["first_name", "last_name", "email"]
        assert _find_name_column(headers, mapping, fields) == "Person"

    def test_returns_none_when_first_name_mapped(self):
        headers = ["Name", "first_name", "Email"]
        mapping = {"first_name": "first_name", "Email": "email"}
        fields = ["first_name", "last_name", "email"]
        assert _find_name_column(headers, mapping, fields) is None

    def test_returns_none_for_companies(self):
        headers = ["Name", "Email"]
        mapping = {"Email": "email"}
        fields = ["name", "email", "industry"]
        assert _find_name_column(headers, mapping, fields) is None

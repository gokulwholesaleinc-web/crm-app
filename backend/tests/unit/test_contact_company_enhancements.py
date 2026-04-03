"""Tests for Phase 5: Contact/Company Enhancements.

Tests cover:
- Company segment CRUD operations
- Contact payment-summary endpoint
- Attachment category field
"""

import io
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.contacts.models import Contact
from src.companies.models import Company
from src.payments.models import StripeCustomer, Payment
from src.attachments.models import Attachment


class TestCompanySegment:
    """Tests for company segment CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_company_with_segment(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Creating a company with segment field stores and returns it."""
        response = await client.post(
            "/api/companies",
            json={
                "name": "Segmented Corp",
                "status": "prospect",
                "segment": "technology",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["segment"] == "technology"
        assert data["name"] == "Segmented Corp"

    @pytest.mark.asyncio
    async def test_create_company_without_segment(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Creating a company without segment defaults to null."""
        response = await client.post(
            "/api/companies",
            json={
                "name": "No Segment Corp",
                "status": "prospect",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["segment"] is None

    @pytest.mark.asyncio
    async def test_update_company_segment(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Updating a company's segment field works correctly."""
        response = await client.patch(
            f"/api/companies/{test_company.id}",
            json={"segment": "healthcare"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["segment"] == "healthcare"

    @pytest.mark.asyncio
    async def test_get_company_includes_segment(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """GET company response includes the segment field."""
        company = Company(
            name="Segment Get Test",
            status="prospect",
            segment="retail",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(company)
        await db_session.commit()
        await db_session.refresh(company)

        response = await client.get(
            f"/api/companies/{company.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["segment"] == "retail"


class TestContactPaymentSummary:
    """Tests for the contact payment-summary endpoint."""

    @pytest.mark.asyncio
    async def test_payment_summary_no_payments(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Payment summary returns zeroes when contact has no payments."""
        response = await client.get(
            f"/api/contacts/{test_contact.id}/payment-summary",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_paid"] == 0.0
        assert data["payment_count"] == 0
        assert data["late_payments"] == 0
        assert data["on_time_rate"] == 100.0
        assert data["last_payment_date"] is None

    @pytest.mark.asyncio
    async def test_payment_summary_with_payments(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
        test_user: User,
    ):
        """Payment summary calculates correctly with succeeded and failed payments."""
        # Create a StripeCustomer linked to the contact
        stripe_customer = StripeCustomer(
            contact_id=test_contact.id,
            stripe_customer_id="cus_test_ps_123",
            email=test_contact.email,
            name=test_contact.full_name,
        )
        db_session.add(stripe_customer)
        await db_session.flush()

        # Create succeeded payments
        payment1 = Payment(
            customer_id=stripe_customer.id,
            amount=100.50,
            currency="USD",
            status="succeeded",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        payment2 = Payment(
            customer_id=stripe_customer.id,
            amount=250.00,
            currency="USD",
            status="succeeded",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        # Create a failed payment (late)
        payment3 = Payment(
            customer_id=stripe_customer.id,
            amount=75.00,
            currency="USD",
            status="failed",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([payment1, payment2, payment3])
        await db_session.commit()

        response = await client.get(
            f"/api/contacts/{test_contact.id}/payment-summary",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_paid"] == 350.50
        assert data["payment_count"] == 2
        assert data["late_payments"] == 1
        # 2 out of 3 total attempts are on-time
        assert data["on_time_rate"] == pytest.approx(66.7, abs=0.1)
        assert data["last_payment_date"] is not None


class TestAttachmentCategory:
    """Tests for attachment category field."""

    @pytest.mark.asyncio
    async def test_upload_attachment_with_category(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Uploading an attachment with a category stores and returns it."""
        file_content = b"test file content for category"
        response = await client.post(
            "/api/attachments/upload",
            files={"file": ("test_doc.txt", io.BytesIO(file_content), "text/plain")},
            data={
                "entity_type": "contacts",
                "entity_id": str(test_contact.id),
                "category": "document",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["category"] == "document"
        assert data["original_filename"] == "test_doc.txt"

    @pytest.mark.asyncio
    async def test_upload_attachment_without_category(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Uploading without category defaults to null."""
        file_content = b"test file no category"
        response = await client.post(
            "/api/attachments/upload",
            files={"file": ("nocategory.txt", io.BytesIO(file_content), "text/plain")},
            data={
                "entity_type": "contacts",
                "entity_id": str(test_contact.id),
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["category"] is None

    @pytest.mark.asyncio
    async def test_upload_attachment_invalid_category(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Uploading with an invalid category returns 400."""
        file_content = b"test file bad category"
        response = await client.post(
            "/api/attachments/upload",
            files={"file": ("badcat.txt", io.BytesIO(file_content), "text/plain")},
            data={
                "entity_type": "contacts",
                "entity_id": str(test_contact.id),
                "category": "invalid_category",
            },
            headers=auth_headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_list_attachments_filter_by_category(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Listing attachments with category filter returns only matching items."""
        # Upload attachments with different categories
        for cat, name in [("document", "doc1.txt"), ("report", "report1.txt"), ("document", "doc2.txt")]:
            await client.post(
                "/api/attachments/upload",
                files={"file": (name, io.BytesIO(b"content"), "text/plain")},
                data={
                    "entity_type": "contacts",
                    "entity_id": str(test_contact.id),
                    "category": cat,
                },
                headers=auth_headers,
            )

        # List all
        response = await client.get(
            f"/api/attachments/contacts/{test_contact.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        all_data = response.json()
        assert all_data["total"] == 3

        # List filtered by document
        response = await client.get(
            f"/api/attachments/contacts/{test_contact.id}",
            params={"category": "document"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        doc_data = response.json()
        assert doc_data["total"] == 2
        for item in doc_data["items"]:
            assert item["category"] == "document"

        # List filtered by report
        response = await client.get(
            f"/api/attachments/contacts/{test_contact.id}",
            params={"category": "report"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        report_data = response.json()
        assert report_data["total"] == 1
        assert report_data["items"][0]["category"] == "report"

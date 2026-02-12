"""
Unit tests for branded quote templates (email + PDF).

Tests for sending branded quote emails, generating branded PDFs,
correct recipient handling, line item rendering, and status transitions.
"""

import pytest
from datetime import date, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.quotes.models import Quote, QuoteLineItem
from src.contacts.models import Contact
from src.companies.models import Company
from src.email.models import EmailQueue
from src.whitelabel.models import Tenant, TenantSettings, TenantUser


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def branded_tenant(db_session: AsyncSession) -> Tenant:
    """Create a tenant with branding for template tests."""
    tenant = Tenant(
        name="Branded Co",
        slug="branded-co",
        domain="branded.example.com",
        is_active=True,
        plan="professional",
        max_users=10,
    )
    db_session.add(tenant)
    await db_session.flush()

    settings = TenantSettings(
        tenant_id=tenant.id,
        company_name="Branded Co Inc",
        logo_url="https://example.com/brand-logo.png",
        primary_color="#3b82f6",
        secondary_color="#6366f1",
        accent_color="#10b981",
        footer_text="Branded Co - All rights reserved",
        email_from_name="Branded Co Sales",
        email_from_address="sales@branded.example.com",
    )
    db_session.add(settings)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest.fixture
async def branded_tenant_user(
    db_session: AsyncSession, branded_tenant: Tenant, test_user: User
) -> TenantUser:
    """Link test_user to the branded tenant as primary admin."""
    tenant_user = TenantUser(
        tenant_id=branded_tenant.id,
        user_id=test_user.id,
        role="admin",
        is_primary=True,
    )
    db_session.add(tenant_user)
    await db_session.commit()
    await db_session.refresh(tenant_user)
    return tenant_user


@pytest.fixture
async def quote_with_contact(
    db_session: AsyncSession, test_user: User, test_contact: Contact
) -> Quote:
    """Create a draft quote linked to a contact with an email."""
    quote = Quote(
        quote_number="QT-2026-TMPL-001",
        title="Branded Template Quote",
        description="Quote for testing branded templates",
        status="draft",
        currency="USD",
        subtotal=0,
        tax_rate=10.0,
        tax_amount=0,
        total=0,
        valid_until=date.today() + timedelta(days=30),
        contact_id=test_contact.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(quote)
    await db_session.flush()

    item1 = QuoteLineItem(
        quote_id=quote.id,
        description="Web Development",
        quantity=40,
        unit_price=150.0,
        discount=0,
        total=6000.0,
        sort_order=0,
    )
    item2 = QuoteLineItem(
        quote_id=quote.id,
        description="Design Services",
        quantity=20,
        unit_price=120.0,
        discount=100.0,
        total=2300.0,
        sort_order=1,
    )
    db_session.add_all([item1, item2])

    quote.subtotal = 8300.0
    quote.tax_amount = 830.0
    quote.total = 9130.0

    await db_session.commit()
    await db_session.refresh(quote)
    return quote


# =============================================================================
# Send Quote Email Tests
# =============================================================================


class TestSendQuoteEmail:
    """Tests for the branded quote email sending endpoint."""

    @pytest.mark.asyncio
    async def test_send_quote_email_creates_email_queue_entry(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        quote_with_contact: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that sending a quote creates an email queue entry."""
        response = await client.post(
            f"/api/quotes/{quote_with_contact.id}/send",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert data["sent_at"] is not None

        # Check email was queued
        result = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == "quotes",
                EmailQueue.entity_id == quote_with_contact.id,
            )
        )
        email = result.scalar_one_or_none()
        assert email is not None
        assert email.to_email == "john.doe@testcompany.com"
        assert "QT-2026-TMPL-001" in email.subject

    @pytest.mark.asyncio
    async def test_send_quote_email_contains_correct_recipient(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        quote_with_contact: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test the email is sent to the correct contact email."""
        response = await client.post(
            f"/api/quotes/{quote_with_contact.id}/send",
            headers=auth_headers,
        )

        assert response.status_code == 200

        result = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == "quotes",
                EmailQueue.entity_id == quote_with_contact.id,
            )
        )
        email = result.scalar_one_or_none()
        assert email is not None
        assert email.to_email == "john.doe@testcompany.com"

    @pytest.mark.asyncio
    async def test_send_quote_email_has_branded_content(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        quote_with_contact: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test the email body contains branded template content."""
        response = await client.post(
            f"/api/quotes/{quote_with_contact.id}/send",
            headers=auth_headers,
        )

        assert response.status_code == 200

        result = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == "quotes",
                EmailQueue.entity_id == quote_with_contact.id,
            )
        )
        email = result.scalar_one_or_none()
        assert email is not None
        # Should contain branded company name
        assert "Branded Co Inc" in email.body
        # Should contain quote number
        assert "QT-2026-TMPL-001" in email.body
        # Should contain line items
        assert "Web Development" in email.body
        assert "Design Services" in email.body

    @pytest.mark.asyncio
    async def test_sending_updates_quote_status_to_sent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        quote_with_contact: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that sending a quote updates its status to 'sent'."""
        assert quote_with_contact.status == "draft"

        response = await client.post(
            f"/api/quotes/{quote_with_contact.id}/send",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert data["sent_at"] is not None

        # Verify in DB
        await db_session.refresh(quote_with_contact)
        assert quote_with_contact.status == "sent"
        assert quote_with_contact.sent_at is not None

    @pytest.mark.asyncio
    async def test_cannot_send_already_sent_quote(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test that sending an already-sent quote returns 400."""
        quote = Quote(
            quote_number="QT-2026-SENT-001",
            title="Already Sent",
            status="sent",
            currency="USD",
            contact_id=test_contact.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(quote)
        await db_session.commit()
        await db_session.refresh(quote)

        response = await client.post(
            f"/api/quotes/{quote.id}/send",
            headers=auth_headers,
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_send_quote_without_contact_still_marks_sent(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test that sending a quote without contact still marks as sent (no email)."""
        quote = Quote(
            quote_number="QT-2026-NOCON-001",
            title="No Contact Quote",
            status="draft",
            currency="USD",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(quote)
        await db_session.commit()
        await db_session.refresh(quote)

        response = await client.post(
            f"/api/quotes/{quote.id}/send",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert data["sent_at"] is not None


# =============================================================================
# Generate Quote PDF Tests
# =============================================================================


class TestGenerateQuotePDF:
    """Tests for the branded quote PDF generation endpoint."""

    @pytest.mark.asyncio
    async def test_generate_quote_pdf_returns_bytes(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        quote_with_contact: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that PDF endpoint returns content."""
        response = await client.get(
            f"/api/quotes/{quote_with_contact.id}/pdf",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert len(response.content) > 0
        assert "Content-Disposition" in response.headers

    @pytest.mark.asyncio
    async def test_generate_quote_pdf_contains_line_items(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        quote_with_contact: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that the PDF contains the correct line items."""
        response = await client.get(
            f"/api/quotes/{quote_with_contact.id}/pdf",
            headers=auth_headers,
        )

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Web Development" in content
        assert "Design Services" in content
        assert "QT-2026-TMPL-001" in content

    @pytest.mark.asyncio
    async def test_generate_quote_pdf_contains_branding(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        quote_with_contact: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that the PDF contains branded elements."""
        response = await client.get(
            f"/api/quotes/{quote_with_contact.id}/pdf",
            headers=auth_headers,
        )

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Branded Co Inc" in content
        assert "#3b82f6" in content

    @pytest.mark.asyncio
    async def test_generate_quote_pdf_contains_totals(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        quote_with_contact: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that the PDF contains correct financial totals."""
        response = await client.get(
            f"/api/quotes/{quote_with_contact.id}/pdf",
            headers=auth_headers,
        )

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "9130.00" in content
        assert "8300.00" in content

    @pytest.mark.asyncio
    async def test_generate_quote_pdf_download_mode(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        quote_with_contact: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that download param sets Content-Disposition to attachment."""
        response = await client.get(
            f"/api/quotes/{quote_with_contact.id}/pdf",
            headers=auth_headers,
            params={"download": True},
        )

        assert response.status_code == 200
        assert "attachment" in response.headers.get("Content-Disposition", "")

    @pytest.mark.asyncio
    async def test_generate_quote_pdf_inline_mode(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        quote_with_contact: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that default mode sets Content-Disposition to inline."""
        response = await client.get(
            f"/api/quotes/{quote_with_contact.id}/pdf",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert "inline" in response.headers.get("Content-Disposition", "")

    @pytest.mark.asyncio
    async def test_generate_pdf_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test that requesting PDF for non-existent quote returns 404."""
        response = await client.get(
            "/api/quotes/99999/pdf",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_pdf_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        quote_with_contact: Quote,
    ):
        """Test that requesting PDF without auth returns 401."""
        response = await client.get(
            f"/api/quotes/{quote_with_contact.id}/pdf",
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_generate_pdf_without_contact_still_works(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test that PDF generation works even without a contact."""
        quote = Quote(
            quote_number="QT-2026-NOCON-PDF",
            title="No Contact PDF Quote",
            status="draft",
            currency="USD",
            subtotal=500.0,
            total=500.0,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(quote)
        await db_session.commit()
        await db_session.refresh(quote)

        response = await client.get(
            f"/api/quotes/{quote.id}/pdf",
            headers=auth_headers,
        )

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "QT-2026-NOCON-PDF" in content
        assert "500.00" in content

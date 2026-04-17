"""Tests for the payments.pdf module (invoice HTML rendering)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.payments.models import Payment, StripeCustomer
from src.payments.pdf import generate_invoice_pdf
from src.whitelabel.models import Tenant, TenantUser


class TestGenerateInvoicePdf:
    """Direct tests for src.payments.pdf.generate_invoice_pdf."""

    @pytest.mark.asyncio
    async def test_returns_html_bytes_with_payment_details(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Returns UTF-8 HTML bytes containing invoice fields."""
        customer = StripeCustomer(
            stripe_customer_id="cus_pdf_direct_1",
            email="direct@example.com",
            name="Direct Customer",
        )
        db_session.add(customer)
        await db_session.flush()

        payment = Payment(
            stripe_payment_intent_id="pi_pdf_direct_1",
            amount=500.00,
            currency="USD",
            status="succeeded",
            payment_method="card",
            customer_id=customer.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.commit()
        await db_session.refresh(payment)

        result = await generate_invoice_pdf(db_session, payment.id)

        assert isinstance(result, bytes)
        html = result.decode("utf-8")
        assert "<!DOCTYPE html>" in html
        assert "INVOICE" in html
        assert "500" in html
        assert "USD" in html
        assert "Direct Customer" in html
        assert f"#{payment.id}" in html

    @pytest.mark.asyncio
    async def test_raises_value_error_for_missing_payment(
        self,
        db_session: AsyncSession,
    ):
        """Raises ValueError with 'not found' when payment_id does not exist."""
        with pytest.raises(ValueError, match="not found"):
            await generate_invoice_pdf(db_session, 999999)

    @pytest.mark.asyncio
    async def test_includes_tenant_branding(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_tenant: Tenant,
        test_tenant_user: TenantUser,
    ):
        """Branding from the payment owner's tenant appears in the output HTML."""
        customer = StripeCustomer(
            stripe_customer_id="cus_pdf_brand_1",
            email="brand@example.com",
            name="Brand Customer",
        )
        db_session.add(customer)
        await db_session.flush()

        payment = Payment(
            stripe_payment_intent_id="pi_pdf_brand_1",
            amount=1200.00,
            currency="GBP",
            status="succeeded",
            customer_id=customer.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(payment)
        await db_session.commit()
        await db_session.refresh(payment)

        result = await generate_invoice_pdf(db_session, payment.id)
        html = result.decode("utf-8")

        assert "Test Tenant Inc" in html

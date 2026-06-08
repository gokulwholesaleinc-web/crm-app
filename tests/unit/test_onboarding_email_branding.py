"""No-mock tests for the branded onboarding e-mails (invite + ready notice).

The onboarding invite and the "your documents are ready" completion notice now
ride the same Link Creative branded wrapper proposals use (a logo header, gold
accent rule, and a CTA pill) instead of a plain-text link. These tests assert
the render helpers produce the branded HTML + working CTA link, and that the
real ``queue_invite`` path lands that HTML on the queued ``EmailQueue`` row.
No mocks — the invite is queued through the real service (the send fails with
no Gmail connection, but the body is persisted before the attempt).
"""

import pytest
from sqlalchemy import select
from src.email.branded_templates import (
    TenantBrandingHelper,
    render_onboarding_invite_email,
    render_onboarding_ready_email,
)
from src.email.models import EmailQueue
from src.onboarding.completion_notices import (
    CLIENT_READY_SUBJECT,
    INVITE_SUBJECT,
    queue_invite,
)
from src.onboarding.packet_service import PacketService

from ._onboarding_helpers import cleanup_packet_storage, make_template

pytestmark = pytest.mark.asyncio

RECIPIENT = "client@example.com"


# --------------------------------------------------------------------------
# Pure render helpers
# --------------------------------------------------------------------------


def test_invite_render_is_branded_html_with_cta_link():
    """The invite body is the branded wrapper with the access link as a CTA."""
    branding = TenantBrandingHelper.get_default_branding()
    link = "https://app.example.com/onboarding/abc123token"
    html = render_onboarding_invite_email(
        branding,
        {"recipient_name": "Dana", "access_link": link, "expires_days": 30},
    )
    assert "<!DOCTYPE html>" in html  # branded wrapper, not plain text
    assert link in html  # the access link survives as the CTA href
    assert "Start onboarding" in html  # the branded CTA pill label
    assert "Hi Dana," in html  # personalised greeting
    assert "30 days" in html


def test_invite_render_without_name_uses_generic_greeting():
    branding = TenantBrandingHelper.get_default_branding()
    html = render_onboarding_invite_email(
        branding, {"access_link": "https://x/onboarding/t", "expires_days": 30}
    )
    assert "Hi there," in html


def test_ready_render_is_branded_html_with_download_cta():
    """The "documents are ready" body is branded with the download link CTA."""
    branding = TenantBrandingHelper.get_default_branding()
    link = "https://app.example.com/onboarding/complete/dl-token"
    html = render_onboarding_ready_email(
        branding, {"download_link": link, "expires_days": 7}
    )
    assert "<!DOCTYPE html>" in html
    assert link in html
    assert "Download documents" in html
    assert "7 days" in html


def test_invite_render_without_link_omits_cta_pill():
    """A missing access_link drops the CTA rather than rendering a dead button."""
    branding = TenantBrandingHelper.get_default_branding()
    html = render_onboarding_invite_email(branding, {"expires_days": 30})
    assert "<!DOCTYPE html>" in html  # still a branded body
    assert "Start onboarding" not in html  # no pill label without a link


def test_ready_render_without_link_omits_cta_pill():
    """A missing download_link drops the CTA rather than rendering a dead button."""
    branding = TenantBrandingHelper.get_default_branding()
    html = render_onboarding_ready_email(branding, {"expires_days": 7})
    assert "<!DOCTYPE html>" in html
    assert "Download documents" not in html


# --------------------------------------------------------------------------
# Wiring: queue_invite lands the branded HTML on the real EmailQueue row
# --------------------------------------------------------------------------


async def _make_packet(db, contact_id, created_by_id):
    template = await make_template(db)
    service = PacketService(db)
    packet, raw = await service.create_packet(
        created_by_id=created_by_id,
        contact_id=contact_id,
        recipient_email=RECIPIENT,
        template_ids=[template.id],
    )
    await db.commit()
    return service, packet, raw


async def test_queue_invite_body_is_branded_html(
    db_session, test_contact, test_user
):
    """queue_invite persists the branded HTML body (the access link survives)."""
    service, packet, _ = await _make_packet(
        db_session, test_contact.id, test_user.id
    )
    try:
        queued = await queue_invite(
            db_session, packet=packet, raw_access_token="raw-access-token-xyz"
        )
        assert queued is True
        row = (
            await db_session.execute(
                select(EmailQueue)
                .where(EmailQueue.entity_type == "onboarding_packets")
                .where(EmailQueue.entity_id == packet.id)
                .where(EmailQueue.subject == INVITE_SUBJECT)
            )
        ).scalar_one()
        assert "<!DOCTYPE html>" in row.body  # branded, not plain text
        assert "/onboarding/raw-access-token-xyz" in row.body
        assert "Start onboarding" in row.body
        # Subject is unchanged so the idempotency key still holds.
        assert row.subject == INVITE_SUBJECT
        assert row.subject != CLIENT_READY_SUBJECT
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)

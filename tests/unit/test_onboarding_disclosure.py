"""No-mock tests for the onboarding ESIGN disclosure SSOT (build-order §5/§3.2).

The disclosure the public page serves post-gate must be byte-identical to the
snapshot persisted on the signature document at create time, and its version
string must be pinned (so older evidence stays attributable). Real packet +
real e-sign document; nothing mocked.
"""

import pytest
from src.onboarding.disclosure import (
    ONBOARDING_ESIGN_DISCLOSURE_VERSION,
    onboarding_esign_disclosure,
)
from src.onboarding.packet_service import PacketService

from ._onboarding_helpers import (
    cleanup_packet_storage,
    make_template,
    signature_field,
)

pytestmark = pytest.mark.asyncio


def test_disclosure_version_is_pinned():
    """The version constant is a stable, non-empty pin."""
    assert isinstance(ONBOARDING_ESIGN_DISCLOSURE_VERSION, str)
    assert ONBOARDING_ESIGN_DISCLOSURE_VERSION  # non-empty
    # It is a single source of truth; the function does not embed a different one.
    assert "onboarding" in ONBOARDING_ESIGN_DISCLOSURE_VERSION


def test_disclosure_text_is_deterministic_and_uses_company_name():
    """Same company name → identical text; the name appears in the body."""
    a = onboarding_esign_disclosure(company_name="Acme Co")
    b = onboarding_esign_disclosure(company_name="Acme Co")
    assert a == b
    assert "Acme Co" in a
    # ESIGN Act framing is present; it is NOT the proposal text ("proposal above").
    assert "ESIGN" in a
    assert "proposal above" not in a


async def test_persisted_snapshot_matches_ssot(db_session, test_contact):
    """The snapshot stored on an e-sign doc equals the SSOT text + version."""
    template = await make_template(
        db_session,
        field_definitions=[signature_field()],
        requires_esign=True,
    )
    service = PacketService(db_session)
    packet, _ = await service.create_packet(
        created_by_id=None,
        contact_id=test_contact.id,
        recipient_email="client@example.com",
        template_ids=[template.id],
    )
    try:
        doc = (await service.load_documents(packet.id))[0]
        assert doc.requires_esign is True
        # Version pinned on the doc.
        assert doc.esign_disclosure_version == ONBOARDING_ESIGN_DISCLOSURE_VERSION
        # Snapshot equals what the SSOT function produces for the resolved
        # company name (no linked company here → the neutral fallback label).
        company_name = await service.resolve_company_name(packet)
        assert doc.esign_disclosure_snapshot == onboarding_esign_disclosure(
            company_name=company_name
        )
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_non_esign_doc_has_no_disclosure_snapshot(db_session, test_contact):
    """A non-e-sign document carries no disclosure snapshot/version."""
    from ._onboarding_helpers import make_questionnaire_template, questionnaire_field

    template = await make_questionnaire_template(
        db_session, field_definitions=[questionnaire_field("name")]
    )
    service = PacketService(db_session)
    packet, _ = await service.create_packet(
        created_by_id=None,
        contact_id=test_contact.id,
        recipient_email="client@example.com",
        template_ids=[template.id],
    )
    try:
        doc = (await service.load_documents(packet.id))[0]
        assert doc.requires_esign is False
        assert doc.esign_disclosure_snapshot is None
        assert doc.esign_disclosure_version is None
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)

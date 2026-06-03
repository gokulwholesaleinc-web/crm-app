"""No-mock tests for the de-PDF kind-membership guard (P1).

The kind-agnostic core now dispatches through ``KIND_HANDLERS[template.kind]``.
A template row may carry a kind the DB CHECK allows (``questionnaire`` /
``upload_request``) BEFORE that kind's handler is registered (P2/P3), so both
send paths must reject an unregistered kind as a clean ``PacketValidationError``
("unknown kind") rather than KeyError-500 or silently no-op. These insert a real
``questionnaire`` template row (no handler in P1) and assert both
``PacketService.create_packet`` (via ``_load_active_templates``) and
``SelectionService.set_selections`` (via ``_assert_templates_active``) reject it,
while a normal esign template still creates a packet with its PDF copied and the
doc's kind frozen to ``esign_pdf``.

The ``needs_pdf_copy=False`` POSITIVE path (a no-PDF questionnaire/upload
template IS sendable) is proven in P2/P3 where those handlers are registered.

No mocks. Real templates, real proposals, real packet creation.
"""

import secrets

import pytest
from src.onboarding.kinds import KIND_HANDLERS
from src.onboarding.models import OnboardingTemplate
from src.onboarding.packet_errors import PacketValidationError
from src.onboarding.packet_service import PacketService
from src.onboarding.selection_service import SelectionService
from src.proposals.models import Proposal

from ._onboarding_helpers import cleanup_packet_storage, make_template

pytestmark = pytest.mark.asyncio


async def _unregistered_kind_template(db) -> OnboardingTemplate:
    """Insert a template with a DB-valid but UNREGISTERED kind (no P1 handler).

    ``questionnaire`` passes the kind CHECK constraint but has no handler in
    KIND_HANDLERS until P2 — exactly the de-PDF guard's target. pdf_path=None is
    legitimate for a non-esign kind (P0-5), so the rejection must be the
    unknown-kind guard, not the no-PDF one.
    """
    assert "questionnaire" not in KIND_HANDLERS  # precondition for this phase
    template = OnboardingTemplate(
        name="Questionnaire (no handler yet)",
        field_definitions=[],
        requires_esign=False,
        is_active=True,
        pdf_path=None,
        kind="questionnaire",
    )
    db.add(template)
    await db.flush()
    return template


async def _make_proposal(db, owner_id, *, contact_id=None):
    proposal = Proposal(
        proposal_number=f"PR-KIND-{secrets.token_hex(4)}",
        title="Kind-gating Proposal",
        status="sent",
        owner_id=owner_id,
        created_by_id=owner_id,
        contact_id=contact_id,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


# --------------------------------------------------------------------------
# create_packet rejects an unregistered kind (_load_active_templates)
# --------------------------------------------------------------------------


async def test_create_packet_rejects_unknown_kind(db_session, test_contact):
    """PacketService.create_packet on a questionnaire template → "unknown kind"."""
    template = await _unregistered_kind_template(db_session)
    service = PacketService(db_session)
    with pytest.raises(PacketValidationError, match="unknown kind"):
        await service.create_packet(
            created_by_id=None,
            contact_id=test_contact.id,
            recipient_email="client@example.com",
            template_ids=[template.id],
        )


# --------------------------------------------------------------------------
# set_selections rejects an unregistered kind (_assert_templates_active)
# --------------------------------------------------------------------------


async def test_set_selections_rejects_unknown_kind(db_session, test_user):
    """SelectionService.set_selections on a questionnaire template → "unknown kind"."""
    proposal = await _make_proposal(db_session, test_user.id)
    template = await _unregistered_kind_template(db_session)
    svc = SelectionService(db_session)
    with pytest.raises(PacketValidationError, match="unknown kind"):
        await svc.set_selections(
            proposal.id, template_ids=[template.id], actor_id=test_user.id
        )


# --------------------------------------------------------------------------
# Sanity: a normal esign template still sends; doc kind + PDF copy are frozen
# --------------------------------------------------------------------------


async def test_esign_template_still_creates_packet(db_session, test_contact):
    """A normal esign template (has PDF) creates a packet; doc.kind=='esign_pdf'
    and the per-packet PDF copy is present (pdf_path not None)."""
    template = await make_template(db_session)  # esign_pdf default, real PDF
    assert template.kind == "esign_pdf"
    service = PacketService(db_session)
    packet, _raw = await service.create_packet(
        created_by_id=None,
        contact_id=test_contact.id,
        recipient_email="client@example.com",
        template_ids=[template.id],
    )
    try:
        docs = await service.load_documents(packet.id)
        assert len(docs) == 1
        doc = docs[0]
        # The doc's kind is frozen from the template, and esign copies the PDF.
        assert doc.kind == "esign_pdf"
        assert doc.pdf_path is not None
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)

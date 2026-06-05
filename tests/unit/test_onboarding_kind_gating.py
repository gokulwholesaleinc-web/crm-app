"""No-mock tests for the de-PDF kind-membership guard (P1).

The kind-agnostic core now dispatches through ``KIND_HANDLERS[template.kind]``.
A template row may carry a kind the DB CHECK allows (``questionnaire`` /
``upload_request``) BEFORE that kind's handler is registered, so both send paths
must reject an unregistered kind as a clean ``PacketValidationError`` ("unknown
kind") rather than KeyError-500 or silently no-op.

Since P2/P3 now REGISTER all three CHECK-valid kinds, there is no longer a
DB-valid-but-unregistered kind to insert (the CHECK constraint is enforced on
SQLite). To keep the unknown-kind guard's coverage real, the negative tests
temporarily DE-REGISTER ``questionnaire`` from the registry (a plain dict —
pop+restore in a try/finally, NO mock) so a CHECK-valid row hits the guard. The
POSITIVE path that P2 unlocks — a no-PDF questionnaire template now DOES create a
packet with ``pdf_path=None`` — is asserted alongside, fulfilling the original
file's "proven in P2/P3" note. A normal esign template still creates a packet
with its PDF copied and the doc's kind frozen to ``esign_pdf``.

No mocks. Real templates, real proposals, real packet creation.
"""

import contextlib
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


@contextlib.contextmanager
def _deregister_kind(kind: str):
    """Temporarily remove ``kind`` from KIND_HANDLERS (real registry, no mock).

    The registry is a plain module-level dict; popping a handler and restoring it
    in a finally re-creates the "CHECK-valid kind whose handler hasn't landed"
    state the unknown-kind guard defends against, now that all three valid kinds
    are registered. Restored even if the body raises so other tests are unaffected.
    """
    handler = KIND_HANDLERS.pop(kind, None)
    try:
        yield
    finally:
        if handler is not None:
            KIND_HANDLERS[kind] = handler


async def _questionnaire_template(db) -> OnboardingTemplate:
    """Insert a real ``questionnaire`` template (CHECK-valid; pdf_path=None).

    pdf_path=None is legitimate for a non-esign kind (P0-5), so when the handler
    is de-registered the rejection is the unknown-kind guard, not the no-PDF one.
    Carries one field — an EMPTY form is now "needs setup" (zero-field guard), so
    a realistic sendable questionnaire must have at least one question.
    """
    template = OnboardingTemplate(
        name="Questionnaire template",
        field_definitions=[
            {"id": "q1", "kind": "short_text", "label": "Q1", "required": True,
             "order": 1}
        ],
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
    """PacketService.create_packet on a CHECK-valid but UNREGISTERED kind →
    "unknown kind" (the handler is de-registered for this assertion)."""
    template = await _questionnaire_template(db_session)
    service = PacketService(db_session)
    with _deregister_kind("questionnaire"), pytest.raises(
        PacketValidationError, match="unknown kind"
    ):
        await service.create_packet(
            created_by_id=None,
            contact_id=test_contact.id,
            recipient_email="client@example.com",
            template_ids=[template.id],
        )


async def test_create_packet_accepts_registered_questionnaire(
    db_session, test_contact
):
    """POSITIVE P2 path: a no-PDF questionnaire template now creates a packet
    with the doc's kind frozen to ``questionnaire`` and ``pdf_path`` left NULL
    (no PDF copy — P0-5)."""
    template = await _questionnaire_template(db_session)
    service = PacketService(db_session)
    packet, _raw = await service.create_packet(
        created_by_id=None,
        contact_id=test_contact.id,
        recipient_email="client@example.com",
        template_ids=[template.id],
    )
    docs = await service.load_documents(packet.id)
    assert len(docs) == 1
    assert docs[0].kind == "questionnaire"
    assert docs[0].pdf_path is None  # non-esign carries no per-packet PDF copy


# --------------------------------------------------------------------------
# set_selections rejects an unregistered kind (_assert_templates_active)
# --------------------------------------------------------------------------


async def test_set_selections_rejects_unknown_kind(db_session, test_user):
    """SelectionService.set_selections on a CHECK-valid but UNREGISTERED kind →
    "unknown kind" (the handler is de-registered for this assertion)."""
    proposal = await _make_proposal(db_session, test_user.id)
    template = await _questionnaire_template(db_session)
    svc = SelectionService(db_session)
    with _deregister_kind("questionnaire"), pytest.raises(
        PacketValidationError, match="unknown kind"
    ):
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

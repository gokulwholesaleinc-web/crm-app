"""No-mock tests for the packet document view-ledger (build-order §10).

The read-before-sign gate: ``record_packet_document_view`` must be
SAVEPOINT-idempotent — the same (document, token) recorded twice yields a
single row (the UNIQUE constraint conflict is contained in a nested
transaction so the outer session survives). Real rows on SQLite; the
``begin_nested`` SAVEPOINT path works on SQLite per the build-order note.
"""

import pytest
from sqlalchemy import func, select
from src.onboarding import tokens
from src.onboarding.models import OnboardingPacketDocumentView
from src.onboarding.packet_service import PacketService
from src.onboarding.view_ledger import (
    get_unviewed_packet_document_ids,
    record_packet_document_view,
)

from ._onboarding_helpers import cleanup_packet_storage, make_template, text_field

pytestmark = pytest.mark.asyncio


async def _packet_with_two_docs(db_session, contact_id):
    t1 = await make_template(db_session, field_definitions=[text_field("a")])
    t2 = await make_template(db_session, field_definitions=[text_field("b")])
    service = PacketService(db_session)
    packet, raw = await service.create_packet(
        created_by_id=None,
        contact_id=contact_id,
        recipient_email="client@example.com",
        template_ids=[t1.id, t2.id],
    )
    docs = await service.load_documents(packet.id)
    return service, packet, raw, docs


async def test_record_view_is_idempotent_for_same_token(db_session, test_contact):
    """Recording the same (doc, token) twice yields exactly ONE row."""
    service, packet, raw, docs = await _packet_with_two_docs(
        db_session, test_contact.id
    )
    try:
        doc = docs[0]
        first = await record_packet_document_view(
            db_session, packet_document_id=doc.id, token=raw, ip_address="1.2.3.4"
        )
        second = await record_packet_document_view(
            db_session, packet_document_id=doc.id, token=raw, ip_address="5.6.7.8"
        )
        assert first is True  # first call inserted
        assert second is False  # second was a no-op (already viewed)

        count = await db_session.execute(
            select(func.count())
            .select_from(OnboardingPacketDocumentView)
            .where(OnboardingPacketDocumentView.packet_document_id == doc.id)
        )
        assert count.scalar() == 1
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_unviewed_ids_track_per_token(db_session, test_contact):
    """get_unviewed shrinks as docs are viewed; empty only when all viewed."""
    service, packet, raw, docs = await _packet_with_two_docs(
        db_session, test_contact.id
    )
    try:
        # Nothing viewed yet → both ids unviewed.
        unviewed = await get_unviewed_packet_document_ids(
            db_session, packet_id=packet.id, token=raw
        )
        assert set(unviewed) == {docs[0].id, docs[1].id}

        # View the first doc.
        await record_packet_document_view(
            db_session, packet_document_id=docs[0].id, token=raw
        )
        unviewed = await get_unviewed_packet_document_ids(
            db_session, packet_id=packet.id, token=raw
        )
        assert unviewed == [docs[1].id]

        # View the second → gate satisfied.
        await record_packet_document_view(
            db_session, packet_document_id=docs[1].id, token=raw
        )
        unviewed = await get_unviewed_packet_document_ids(
            db_session, packet_id=packet.id, token=raw
        )
        assert unviewed == []
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_views_are_scoped_to_the_token_hash(db_session, test_contact):
    """A view recorded under one token doesn't satisfy a different token's gate."""
    service, packet, raw, docs = await _packet_with_two_docs(
        db_session, test_contact.id
    )
    try:
        await record_packet_document_view(
            db_session, packet_document_id=docs[0].id, token=raw
        )
        # A DIFFERENT token (a forwarded link can't piggyback) sees both unviewed.
        other_token = tokens.mint_token()
        unviewed = await get_unviewed_packet_document_ids(
            db_session, packet_id=packet.id, token=other_token
        )
        assert set(unviewed) == {docs[0].id, docs[1].id}
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)

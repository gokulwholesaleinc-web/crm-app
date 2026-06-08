"""No-mock tests for the onboarding wizard audit-remediation fixes.

Covers the backend slice: description length caps (BE-DESC-LEN), the
questionnaire label control-character guard (BE-NEWLINE), and the
``_mark_failed`` traceback fix (BE-LOG) — the H1 signature choke point logs a
deliberate rejection at error level WITHOUT a spurious ``NoneType: None``
traceback, while the Phase-B stamp failure still captures the active one.
"""

import logging

import pytest
from pydantic import ValidationError
from src.onboarding import completion
from src.onboarding.bundle_schemas import BundleCreate, BundleUpdate
from src.onboarding.kinds.questionnaire import validate_questionnaire_definitions
from src.onboarding.models import OnboardingPacket
from src.onboarding.packet_service import PacketService
from src.onboarding.schemas import TemplateCreate, TemplateUpdate
from src.onboarding.service import FieldDefinitionError

from ._onboarding_helpers import cleanup_packet_storage, make_template

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------
# BE-DESC-LEN — description is capped (was unbounded Text → storage DoS)
# --------------------------------------------------------------------------


def test_template_create_description_over_cap_rejected():
    TemplateCreate(name="OK", description="x" * 2000)  # at the cap: fine
    with pytest.raises(ValidationError):
        TemplateCreate(name="OK", description="x" * 2001)


def test_template_update_description_over_cap_rejected():
    with pytest.raises(ValidationError):
        TemplateUpdate(description="x" * 2001)


def test_bundle_description_over_cap_rejected():
    BundleCreate(name="OK", description="x" * 2000)
    with pytest.raises(ValidationError):
        BundleCreate(name="OK", description="x" * 2001)
    with pytest.raises(ValidationError):
        BundleUpdate(description="x" * 2001)


# --------------------------------------------------------------------------
# BE-NEWLINE — labels reject embedded line breaks / tabs
# --------------------------------------------------------------------------


def test_questionnaire_field_label_with_newline_rejected():
    with pytest.raises(FieldDefinitionError, match="line breaks"):
        validate_questionnaire_definitions(
            [{"id": "name", "kind": "short_text", "label": "First\nLast"}]
        )


def test_questionnaire_option_label_with_tab_rejected():
    with pytest.raises(FieldDefinitionError, match="line breaks"):
        validate_questionnaire_definitions(
            [
                {
                    "id": "color",
                    "kind": "single_choice",
                    "label": "Color",
                    "options": [{"value": "r", "label": "Re\td"}],
                }
            ]
        )


def test_questionnaire_clean_single_line_label_accepted():
    # The fix must not reject ordinary single-line labels.
    validate_questionnaire_definitions(
        [{"id": "name", "kind": "short_text", "label": "Full name"}]
    )


# --------------------------------------------------------------------------
# BE-LOG — _mark_failed only attaches a traceback when one is active
# --------------------------------------------------------------------------


async def _completing_packet(db, contact_id, created_by_id):
    template = await make_template(db)
    service = PacketService(db)
    packet, _ = await service.create_packet(
        created_by_id=created_by_id,
        contact_id=contact_id,
        recipient_email="client@example.com",
        template_ids=[template.id],
    )
    packet.status = "completing"
    await db.commit()
    return service, packet


async def test_mark_failed_without_active_exception_logs_no_traceback(
    db_session, test_contact, test_user, caplog
):
    """The H1 choke calls _mark_failed with no exception active (exc_info=False)."""
    service, packet = await _completing_packet(
        db_session, test_contact.id, test_user.id
    )
    try:
        with caplog.at_level(logging.ERROR, logger=completion.logger.name):
            await completion._mark_failed(
                db_session, packet.id, "no signature field"
            )
        rec = next(r for r in caplog.records if "completion failed" in r.message)
        # No active exception → no traceback attached (was a bogus NoneType: None).
        assert not rec.exc_info
        refreshed = await db_session.get(OnboardingPacket, packet.id)
        assert refreshed.status == "completion_failed"
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)


async def test_mark_failed_with_active_exception_captures_traceback(
    db_session, test_contact, test_user, caplog
):
    """The Phase-B stamp failure passes exc_info=True so Sentry gets the cause."""
    service, packet = await _completing_packet(
        db_session, test_contact.id, test_user.id
    )
    try:
        with caplog.at_level(logging.ERROR, logger=completion.logger.name):
            try:
                raise RuntimeError("R2 write failed")
            except RuntimeError:
                await completion._mark_failed(
                    db_session, packet.id, "R2 write failed", exc_info=True
                )
        rec = next(r for r in caplog.records if "completion failed" in r.message)
        assert rec.exc_info is not None and rec.exc_info[0] is RuntimeError
    finally:
        await cleanup_packet_storage(db_session, service, packet.id)

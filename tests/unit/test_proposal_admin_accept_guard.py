"""No-mock tests for the admin-accept manual-confirmation guard (§E).

The offline admin accept must refuse (409) when the proposal has a signature
area but no signature on file, unless the caller re-submits with
``acknowledge_unsigned=true`` — which then accepts AND writes a durable audit
Activity. A proposal with no signature target accepts without a prompt. The
public e-sign accept path is untouched (regression). No mocks.
"""

import secrets

import pytest
from sqlalchemy import select

from src.activities.models import Activity
from src.proposals.models import Proposal, ProposalSigningDocument

pytestmark = pytest.mark.asyncio


async def _make_sent_proposal(db, owner_id, **overrides):
    proposal = Proposal(
        proposal_number=f"PR-GUARD-{secrets.token_hex(4)}",
        title="Guard Proposal",
        status="sent",
        owner_id=owner_id,
        created_by_id=owner_id,
        **overrides,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


async def _audit_activities(db, proposal_id):
    return (
        await db.execute(
            select(Activity)
            .where(Activity.entity_type == "proposals")
            .where(Activity.entity_id == proposal_id)
            .where(Activity.subject == "Proposal manually accepted without signature")
        )
    ).scalars().all()


async def test_unsigned_master_contract_target_409_without_ack(
    client, db_session, test_admin_user, admin_auth_headers
):
    """A master-contract sig box with no signature → 409 without acknowledgement."""
    proposal = await _make_sent_proposal(
        db_session,
        test_admin_user.id,
        master_contract_pdf_path="obj://contract.pdf",
        signature_field_coords={"page": 1, "x": 1, "y": 1, "w": 10, "h": 10},
    )
    resp = await client.post(
        f"/api/proposals/{proposal.id}/accept", headers=admin_auth_headers
    )
    assert resp.status_code == 409, resp.text
    assert "signature area" in resp.json()["detail"]
    # Status unchanged (not accepted).
    await db_session.refresh(proposal)
    assert proposal.status != "accepted"


async def test_unsigned_accept_with_ack_succeeds_and_audits(
    client, db_session, test_admin_user, admin_auth_headers
):
    """acknowledge_unsigned=true accepts + writes the audit Activity."""
    proposal = await _make_sent_proposal(
        db_session,
        test_admin_user.id,
        master_contract_pdf_path="obj://contract.pdf",
    )
    resp = await client.post(
        f"/api/proposals/{proposal.id}/accept?acknowledge_unsigned=true",
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"

    acts = await _audit_activities(db_session, proposal.id)
    assert len(acts) == 1
    assert "manually accepted without signature by" in acts[0].description


async def test_signing_doc_with_sig_box_triggers_guard(
    client, db_session, test_admin_user, admin_auth_headers
):
    """A per-doc signing-document sig box (no master contract) also gates."""
    proposal = await _make_sent_proposal(db_session, test_admin_user.id)
    db_session.add(
        ProposalSigningDocument(
            proposal_id=proposal.id,
            original_filename="agreement.pdf",
            pdf_path="obj://agreement.pdf",
            signature_field_coords={"page": 1, "x": 1, "y": 1, "w": 10, "h": 10},
        )
    )
    await db_session.commit()

    blocked = await client.post(
        f"/api/proposals/{proposal.id}/accept", headers=admin_auth_headers
    )
    assert blocked.status_code == 409, blocked.text

    ok = await client.post(
        f"/api/proposals/{proposal.id}/accept?acknowledge_unsigned=true",
        headers=admin_auth_headers,
    )
    assert ok.status_code == 200, ok.text


async def test_no_signature_target_accepts_without_prompt(
    client, db_session, test_admin_user, admin_auth_headers
):
    """A proposal with no signature target accepts immediately + no audit row."""
    proposal = await _make_sent_proposal(db_session, test_admin_user.id)
    resp = await client.post(
        f"/api/proposals/{proposal.id}/accept", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"
    assert await _audit_activities(db_session, proposal.id) == []


async def test_already_signed_proposal_accepts_without_prompt(
    client, db_session, test_admin_user, admin_auth_headers
):
    """A target WITH a captured signature_image does not gate."""
    proposal = await _make_sent_proposal(
        db_session,
        test_admin_user.id,
        master_contract_pdf_path="obj://contract.pdf",
        signature_image=b"\x89PNG\r\n\x1a\n",
    )
    resp = await client.post(
        f"/api/proposals/{proposal.id}/accept", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert await _audit_activities(db_session, proposal.id) == []

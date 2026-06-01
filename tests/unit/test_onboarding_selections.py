"""No-mock tests for the proposal→onboarding-template selection endpoints (§A).

Exercises ``SelectionService`` directly AND the authenticated staff routes via
the ASGI ``client`` fixture: list (ordered), set/replace (retired-template 422,
duplicate 422), reorder (respecting the unique-order constraint via the
temp-offset two-pass), remove (404 for a foreign selection). Real templates +
real proposals; nothing mocked.
"""

import secrets

import pytest
from sqlalchemy import select

from src.onboarding.models import OnboardingTemplate, ProposalOnboardingSelection
from src.onboarding.packet_errors import (
    PacketNotFoundError,
    PacketValidationError,
)
from src.onboarding.selection_service import (
    SelectionService,
    active_selection_template_ids,
)
from src.proposals.models import Proposal

from ._onboarding_helpers import make_template

pytestmark = pytest.mark.asyncio


async def _make_proposal(db, owner_id, *, contact_id=None, company_id=None):
    proposal = Proposal(
        proposal_number=f"PR-SEL-{secrets.token_hex(4)}",
        title="Selection Proposal",
        status="sent",
        owner_id=owner_id,
        created_by_id=owner_id,
        contact_id=contact_id,
        company_id=company_id,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


# --------------------------------------------------------------------------
# Service-level
# --------------------------------------------------------------------------


async def test_set_selections_rejects_template_without_pdf(db_session, test_user):
    """A template with no uploaded PDF is a 422 at SET time, not a silent
    acceptance-time trigger failure (the trigger's create_packet needs a PDF)."""
    proposal = await _make_proposal(db_session, test_user.id)
    no_pdf = OnboardingTemplate(
        name="No PDF Template",
        field_definitions=[],
        requires_esign=False,
        is_active=True,
        pdf_path=None,
    )
    db_session.add(no_pdf)
    await db_session.flush()
    svc = SelectionService(db_session)
    with pytest.raises(PacketValidationError, match="no PDF"):
        await svc.set_selections(
            proposal.id, template_ids=[no_pdf.id], actor_id=test_user.id
        )


async def test_set_and_list_selections_orders_by_display_order(
    db_session, test_user
):
    """set_selections assigns 0..N-1 display_order; list returns that order."""
    proposal = await _make_proposal(db_session, test_user.id)
    t1 = await make_template(db_session)
    t2 = await make_template(db_session)
    t3 = await make_template(db_session)
    svc = SelectionService(db_session)

    rows = await svc.set_selections(
        proposal.id, template_ids=[t3.id, t1.id, t2.id], actor_id=test_user.id
    )
    assert [r.template_id for r in rows] == [t3.id, t1.id, t2.id]
    assert [r.display_order for r in rows] == [0, 1, 2]

    listed = await svc.list_selections(proposal.id)
    assert [r.template_id for r in listed] == [t3.id, t1.id, t2.id]


async def test_set_selections_rejects_retired_template_422(db_session, test_user):
    """A retired (is_active=false) template is a clean PacketValidationError."""
    proposal = await _make_proposal(db_session, test_user.id)
    retired = await make_template(db_session, is_active=False)
    svc = SelectionService(db_session)

    with pytest.raises(PacketValidationError):
        await svc.set_selections(
            proposal.id, template_ids=[retired.id], actor_id=test_user.id
        )


async def test_set_selections_rejects_duplicates(db_session, test_user):
    """A duplicate template id in the set list is a 422 (not a constraint 500)."""
    proposal = await _make_proposal(db_session, test_user.id)
    t1 = await make_template(db_session)
    svc = SelectionService(db_session)

    with pytest.raises(PacketValidationError):
        await svc.set_selections(
            proposal.id, template_ids=[t1.id, t1.id], actor_id=test_user.id
        )


async def test_reorder_respects_unique_order_constraint(db_session, test_user):
    """Reorder fully reverses the order without tripping uq_..._order.

    The (proposal_id, display_order) unique constraint would collide under a
    naive per-row UPDATE; the temp-offset two-pass must let a full reversal
    succeed and persist contiguous 0..N-1 orders.
    """
    proposal = await _make_proposal(db_session, test_user.id)
    templates = [await make_template(db_session) for _ in range(3)]
    svc = SelectionService(db_session)
    rows = await svc.set_selections(
        proposal.id,
        template_ids=[t.id for t in templates],
        actor_id=test_user.id,
    )
    await db_session.commit()
    reversed_ids = [r.id for r in reversed(rows)]

    reordered = await svc.reorder(
        proposal.id, ordered_ids=reversed_ids, actor_id=test_user.id
    )
    await db_session.commit()

    assert [r.id for r in reordered] == reversed_ids
    assert [r.display_order for r in reordered] == [0, 1, 2]
    # And the rows are contiguous + collision-free in the DB.
    persisted = (
        await db_session.execute(
            select(ProposalOnboardingSelection.display_order)
            .where(ProposalOnboardingSelection.proposal_id == proposal.id)
            .order_by(ProposalOnboardingSelection.display_order)
        )
    ).scalars().all()
    assert list(persisted) == [0, 1, 2]


async def test_reorder_rejects_non_permutation(db_session, test_user):
    """ordered_ids that aren't exactly the current ids is a 422."""
    proposal = await _make_proposal(db_session, test_user.id)
    t1 = await make_template(db_session)
    svc = SelectionService(db_session)
    rows = await svc.set_selections(
        proposal.id, template_ids=[t1.id], actor_id=test_user.id
    )
    with pytest.raises(PacketValidationError):
        await svc.reorder(
            proposal.id, ordered_ids=[rows[0].id, 99999], actor_id=test_user.id
        )


async def test_remove_foreign_selection_404(db_session, test_user):
    """Removing a selection that isn't on this proposal raises PacketNotFoundError."""
    p1 = await _make_proposal(db_session, test_user.id)
    p2 = await _make_proposal(db_session, test_user.id)
    t1 = await make_template(db_session)
    svc = SelectionService(db_session)
    rows = await svc.set_selections(
        p1.id, template_ids=[t1.id], actor_id=test_user.id
    )
    with pytest.raises(PacketNotFoundError):
        await svc.remove(p2.id, rows[0].id)


async def test_active_selection_template_ids_skips_retired(db_session, test_user):
    """The trigger read drops a template retired AFTER it was selected."""
    proposal = await _make_proposal(db_session, test_user.id)
    keep = await make_template(db_session)
    drop = await make_template(db_session)
    svc = SelectionService(db_session)
    await svc.set_selections(
        proposal.id, template_ids=[keep.id, drop.id], actor_id=test_user.id
    )
    # Retire one template after selection.
    drop.is_active = False
    await db_session.flush()

    ids = await active_selection_template_ids(db_session, proposal.id)
    assert ids == [keep.id]


# --------------------------------------------------------------------------
# Route-level (auth + entity-access)
# --------------------------------------------------------------------------


async def test_selection_routes_full_cycle(
    client, db_session, test_user, test_contact, admin_auth_headers
):
    """PUT → GET → reorder → DELETE through the real routes (admin sees all)."""
    proposal = await _make_proposal(
        db_session, test_user.id, contact_id=test_contact.id
    )
    t1 = await make_template(db_session)
    t2 = await make_template(db_session)
    await db_session.commit()

    put = await client.put(
        f"/api/onboarding/proposals/{proposal.id}/selections",
        headers=admin_auth_headers,
        json={"template_ids": [t1.id, t2.id]},
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert [r["template_id"] for r in body] == [t1.id, t2.id]
    ids = [r["id"] for r in body]

    got = await client.get(
        f"/api/onboarding/proposals/{proposal.id}/selections",
        headers=admin_auth_headers,
    )
    assert got.status_code == 200
    assert [r["template_id"] for r in got.json()] == [t1.id, t2.id]

    reordered = await client.post(
        f"/api/onboarding/proposals/{proposal.id}/selections/reorder",
        headers=admin_auth_headers,
        json={"ordered_ids": list(reversed(ids))},
    )
    assert reordered.status_code == 200
    assert [r["template_id"] for r in reordered.json()] == [t2.id, t1.id]

    deleted = await client.delete(
        f"/api/onboarding/proposals/{proposal.id}/selections/{ids[0]}",
        headers=admin_auth_headers,
    )
    assert deleted.status_code == 204
    remaining = await client.get(
        f"/api/onboarding/proposals/{proposal.id}/selections",
        headers=admin_auth_headers,
    )
    assert len(remaining.json()) == 1


async def test_set_selections_route_retired_template_422(
    client, db_session, test_user, test_contact, admin_auth_headers
):
    """The PUT route surfaces a retired-template selection as a 422."""
    proposal = await _make_proposal(
        db_session, test_user.id, contact_id=test_contact.id
    )
    retired = await make_template(db_session, is_active=False)
    await db_session.commit()

    resp = await client.put(
        f"/api/onboarding/proposals/{proposal.id}/selections",
        headers=admin_auth_headers,
        json={"template_ids": [retired.id]},
    )
    assert resp.status_code == 422, resp.text

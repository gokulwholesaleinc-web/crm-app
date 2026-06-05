"""No-mock tests for onboarding clone / from-starter / bundle wizard + CRUD (§7).

Everything runs against the real in-memory SQLite DB through the ``client``
fixture (routes) or the services directly — nothing is mocked. HONEST per §3/B3:
the bundle ``FOR UPDATE`` lock and the auto-suffix SAVEPOINT race are no-ops /
single-threaded here (review-asserted, not race-proven); these tests cover the
same-session behaviour. ON DELETE CASCADE is a Postgres-only guarantee (SQLite
ignores it without the FK pragma) — the delete test asserts the bundle row is
gone, not the item cascade.
"""

import uuid

import pytest
from sqlalchemy import func, select
from src.auth.models import User
from src.onboarding.bundle_schemas import BundleWizardItem
from src.onboarding.bundle_service import BundleService
from src.onboarding.models import (
    OnboardingTemplate,
    OnboardingTemplateBundle,
    OnboardingTemplateBundleItem,
)
from src.onboarding.packet_errors import PacketNotFoundError, PacketValidationError
from src.onboarding.packet_service import PacketService
from src.onboarding.selection_service import SelectionService
from src.onboarding.service import (
    DuplicateTemplateNameError,
    FieldDefinitionError,
    OnboardingTemplateService,
)
from src.onboarding.starter_definitions import onboarding_template_specs
from src.proposals.models import Proposal

from ._onboarding_helpers import make_template

pytestmark = pytest.mark.asyncio


def _qfield(fid: str = "q1", **over) -> dict:
    field = {"id": fid, "kind": "short_text", "label": "Q1", "required": True,
             "order": 1}
    field.update(over)
    return field


async def _questionnaire(
    db, *, name=None, fields=None, is_active=True, service_tag=None,
    description="A questionnaire", owner_id=None,
):
    template = OnboardingTemplate(
        name=name or f"Q {uuid.uuid4().hex[:8]}",
        description=description,
        service_tag=service_tag,
        kind="questionnaire",
        field_definitions=fields if fields is not None else [_qfield()],
        requires_esign=False,
        is_active=is_active,
        pdf_path=None,
        owner_id=owner_id,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


async def _esign_no_pdf(db, *, name=None, is_active=True):
    template = OnboardingTemplate(
        name=name or f"Esign {uuid.uuid4().hex[:8]}",
        kind="esign_pdf",
        field_definitions=[],
        requires_esign=False,
        is_active=is_active,
        pdf_path=None,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


# ===========================================================================
# _build_template (§4.2)
# ===========================================================================
async def test_build_template_sets_owner_and_creator(test_user):
    t = OnboardingTemplateService._build_template(
        current_user=test_user, name="X", description=None, service_tag=None,
        requires_esign=False, kind="questionnaire", field_definitions=[_qfield()],
    )
    assert t.owner_id == test_user.id
    assert t.created_by_id == test_user.id


async def test_build_template_rejects_esign_with_fields(test_user):
    with pytest.raises(FieldDefinitionError):
        OnboardingTemplateService._build_template(
            current_user=test_user, name="X", description=None, service_tag=None,
            requires_esign=False, kind="esign_pdf",
            field_definitions=[{"id": "a", "kind": "text", "label": "A",
                                "page": 1, "x": 1, "y": 1, "w": 1, "h": 1}],
        )


async def test_build_template_rejects_contact_email_prefill(test_user):
    """The shared ALLOWED_PREFILL allowlist rejects contact.email (PII)."""
    with pytest.raises(FieldDefinitionError):
        OnboardingTemplateService._build_template(
            current_user=test_user, name="X", description=None, service_tag=None,
            requires_esign=False, kind="questionnaire",
            field_definitions=[_qfield(prefill="contact.email")],
        )


# ===========================================================================
# Clone (§4.3) — service level
# ===========================================================================
async def test_clone_copies_fields_and_is_independent(db_session, test_user):
    source = await _questionnaire(
        db_session, fields=[_qfield("a"), _qfield("b", order=2)],
        service_tag="website", description="src desc",
    )
    svc = OnboardingTemplateService(db_session)
    clone = await svc.clone_template(source, current_user=test_user, name="Clone A")
    assert clone.id != source.id
    assert clone.kind == "questionnaire"
    assert clone.description == "src desc"
    assert clone.service_tag == "website"
    assert [f["id"] for f in clone.field_definitions] == ["a", "b"]
    assert clone.owner_id == test_user.id
    # Independent list: mutating the clone doesn't touch the source.
    clone.field_definitions.append(_qfield("c", order=3))
    assert len(source.field_definitions) == 2


async def test_clone_refuses_esign_source(db_session, test_user):
    source = await make_template(db_session)  # esign_pdf + PDF
    svc = OnboardingTemplateService(db_session)
    with pytest.raises(FieldDefinitionError):
        await svc.clone_template(source, current_user=test_user, name="C")


async def test_clone_refuses_retired_source(db_session, test_user):
    source = await _questionnaire(db_session, is_active=False)
    svc = OnboardingTemplateService(db_session)
    with pytest.raises(FieldDefinitionError):
        await svc.clone_template(source, current_user=test_user, name="C")


async def test_clone_auto_suffix_when_name_omitted(db_session, test_user):
    source = await _questionnaire(db_session, name="Intake Form")
    svc = OnboardingTemplateService(db_session)
    clone = await svc.clone_template(source, current_user=test_user, name=None)
    assert clone.name == "Intake Form (copy)"


async def test_clone_auto_suffix_picks_next_free(db_session, test_user):
    """A same-session "(copy)" collision bumps to "(copy 2)" (pre-query path,
    V3-2). The SAVEPOINT backstop guards a real race (not reproduced here)."""
    source = await _questionnaire(db_session, name="Intake Form")
    svc = OnboardingTemplateService(db_session)
    first = await svc.clone_template(source, current_user=test_user, name=None)
    assert first.name == "Intake Form (copy)"
    second = await svc.clone_template(source, current_user=test_user, name=None)
    assert second.name == "Intake Form (copy 2)"


async def test_clone_explicit_name_collision_422(db_session, test_user):
    source = await _questionnaire(db_session, name="Source")
    await _questionnaire(db_session, name="Taken Name")
    svc = OnboardingTemplateService(db_session)
    with pytest.raises(DuplicateTemplateNameError):
        await svc.clone_template(source, current_user=test_user, name="Taken Name")


async def test_create_from_starter_fields_correct(db_session, test_user):
    spec = next(s for s in onboarding_template_specs() if s["kind"] == "questionnaire")
    svc = OnboardingTemplateService(db_session)
    t = await svc.create_from_starter(spec, current_user=test_user, name="From Starter")
    assert t.kind == spec["kind"]
    assert t.name == "From Starter"
    assert [f["id"] for f in t.field_definitions] == [
        f["id"] for f in spec["field_definitions"]
    ]
    assert t.owner_id == test_user.id


# ===========================================================================
# Clone / from-starter / starters — route level
# ===========================================================================
async def test_clone_route_404_missing(client, admin_auth_headers):
    resp = await client.post(
        "/api/onboarding/templates/999999/clone",
        headers=admin_auth_headers, json={},
    )
    assert resp.status_code == 404, resp.text


async def test_clone_route_esign_422(client, db_session, admin_auth_headers):
    source = await make_template(db_session)  # esign + PDF
    await db_session.commit()
    resp = await client.post(
        f"/api/onboarding/templates/{source.id}/clone",
        headers=admin_auth_headers, json={},
    )
    assert resp.status_code == 422, resp.text


async def test_clone_route_perm_403(client, db_session, viewer_auth_headers):
    source = await _questionnaire(db_session)
    await db_session.commit()
    resp = await client.post(
        f"/api/onboarding/templates/{source.id}/clone",
        headers=viewer_auth_headers, json={},
    )
    assert resp.status_code == 403, resp.text


async def test_from_starter_route_201(client, admin_auth_headers):
    spec = next(s for s in onboarding_template_specs() if s["kind"] == "upload_request")
    resp = await client.post(
        "/api/onboarding/templates/from-starter",
        headers=admin_auth_headers,
        json={"starter_key": spec["key"], "name": "My Upload Doc"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "My Upload Doc"
    assert body["kind"] == "upload_request"


async def test_from_starter_route_unknown_key_404(client, admin_auth_headers):
    resp = await client.post(
        "/api/onboarding/templates/from-starter",
        headers=admin_auth_headers, json={"starter_key": "no-such-starter"},
    )
    assert resp.status_code == 404, resp.text


async def test_from_starter_route_perm_403(client, viewer_auth_headers):
    resp = await client.post(
        "/api/onboarding/templates/from-starter",
        headers=viewer_auth_headers, json={"starter_key": "admin-information"},
    )
    assert resp.status_code == 403, resp.text


async def test_starters_route_lists_all(client, admin_auth_headers):
    resp = await client.get(
        "/api/onboarding/templates/starters", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == len(onboarding_template_specs())
    for item in body:
        assert item["key"] and item["name"] and item["kind"]
        assert item["kind"] in ("questionnaire", "upload_request")


# ===========================================================================
# Wizard create (§4.4)
# ===========================================================================
def _wizard_payload(name, items):
    return {"name": name, "items": items}


async def test_wizard_creates_bundle_mixed_items(
    client, db_session, admin_auth_headers
):
    source = await _questionnaire(db_session, name="Existing Q")
    starter = next(
        s for s in onboarding_template_specs() if s["kind"] == "questionnaire"
    )
    await db_session.commit()
    resp = await client.post(
        "/api/onboarding/template-bundles",
        headers=admin_auth_headers,
        json=_wizard_payload(
            "Mixed Packet",
            [
                {"source": "clone", "source_template_id": source.id,
                 "name": "Doc Clone"},
                {"source": "starter", "starter_key": starter["key"],
                 "name": "Doc Starter"},
                {"source": "blank", "kind": "questionnaire", "name": "Doc Blank",
                 "field_definitions": [_qfield()]},
            ],
        ),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Mixed Packet"
    assert body["item_count"] == 3
    members = body["members"]
    assert [m["display_order"] for m in members] == [0, 1, 2]
    assert [m["name"] for m in members] == ["Doc Clone", "Doc Starter", "Doc Blank"]
    # Each minted a NEW template (distinct from the clone source).
    assert all(m["template_id"] != source.id for m in members)


async def test_wizard_rejects_empty_items_422(client, admin_auth_headers):
    resp = await client.post(
        "/api/onboarding/template-bundles",
        headers=admin_auth_headers, json=_wizard_payload("Empty", []),
    )
    assert resp.status_code == 422, resp.text


async def test_wizard_all_or_nothing_on_bad_item(
    client, db_session, admin_auth_headers
):
    """An e-sign clone item fails the whole batch: zero templates, no bundle."""
    esign = await make_template(db_session)  # esign + PDF — not cloneable
    good_q = await _questionnaire(db_session, name="Good Source")
    await db_session.commit()
    before_templates = (
        await db_session.execute(select(func.count()).select_from(OnboardingTemplate))
    ).scalar_one()
    resp = await client.post(
        "/api/onboarding/template-bundles",
        headers=admin_auth_headers,
        json=_wizard_payload(
            "Doomed Packet",
            [
                {"source": "clone", "source_template_id": good_q.id,
                 "name": "Brand New Doc Name"},
                {"source": "clone", "source_template_id": esign.id,
                 "name": "Another New Doc Name"},
            ],
        ),
    )
    assert resp.status_code == 422, resp.text
    after_templates = (
        await db_session.execute(select(func.count()).select_from(OnboardingTemplate))
    ).scalar_one()
    assert after_templates == before_templates  # nothing partial
    bundles = (
        await db_session.execute(
            select(func.count()).select_from(OnboardingTemplateBundle)
        )
    ).scalar_one()
    assert bundles == 0


async def test_wizard_duplicate_name_within_batch_422(client, admin_auth_headers):
    resp = await client.post(
        "/api/onboarding/template-bundles",
        headers=admin_auth_headers,
        json=_wizard_payload(
            "Dup Batch",
            [
                {"source": "blank", "kind": "questionnaire", "name": "Same Name",
                 "field_definitions": [_qfield()]},
                {"source": "blank", "kind": "questionnaire", "name": "Same Name",
                 "field_definitions": [_qfield()]},
            ],
        ),
    )
    assert resp.status_code == 422, resp.text


async def test_wizard_existing_template_name_collision_422(
    client, db_session, admin_auth_headers
):
    await _questionnaire(db_session, name="Already Exists Doc")
    await db_session.commit()
    before = (
        await db_session.execute(select(func.count()).select_from(OnboardingTemplate))
    ).scalar_one()
    resp = await client.post(
        "/api/onboarding/template-bundles",
        headers=admin_auth_headers,
        json=_wizard_payload(
            "Collision Packet",
            [{"source": "blank", "kind": "questionnaire",
              "name": "Already Exists Doc", "field_definitions": [_qfield()]}],
        ),
    )
    assert resp.status_code == 422, resp.text
    after = (
        await db_session.execute(select(func.count()).select_from(OnboardingTemplate))
    ).scalar_one()
    assert after == before


async def test_wizard_blank_esign_item_not_send_ready(
    client, admin_auth_headers
):
    """A blank e-sign document has no PDF, so the packet "needs setup" (§4.7)."""
    resp = await client.post(
        "/api/onboarding/template-bundles",
        headers=admin_auth_headers,
        json=_wizard_payload(
            "Needs Setup Packet",
            [{"source": "blank", "kind": "esign_pdf", "name": "Agreement PDF"}],
        ),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["send_ready"] is False
    member = body["members"][0]
    assert member["send_ready"] is False
    assert "PDF" in (member["send_reason"] or "")


# ===========================================================================
# Bundle CRUD (§4.6)
# ===========================================================================
async def _create_bundle(client, headers, name, items):
    resp = await client.post(
        "/api/onboarding/template-bundles", headers=headers,
        json={"name": name, "items": items},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _blank_q(name):
    return {"source": "blank", "kind": "questionnaire", "name": name,
            "field_definitions": [_qfield()]}


async def test_bundle_list_and_detail(client, admin_auth_headers):
    created = await _create_bundle(
        client, admin_auth_headers, "List Me",
        [_blank_q("L1"), _blank_q("L2")],
    )
    lst = await client.get(
        "/api/onboarding/template-bundles", headers=admin_auth_headers
    )
    assert lst.status_code == 200
    ids = [b["id"] for b in lst.json()]
    assert created["id"] in ids
    summary = next(b for b in lst.json() if b["id"] == created["id"])
    assert summary["item_count"] == 2
    assert summary["send_ready"] is True  # two questionnaires, no PDF needed

    detail = await client.get(
        f"/api/onboarding/template-bundles/{created['id']}",
        headers=admin_auth_headers,
    )
    assert detail.status_code == 200
    assert [m["name"] for m in detail.json()["members"]] == ["L1", "L2"]


async def test_bundle_reorder_two_pass_no_collision(client, admin_auth_headers):
    created = await _create_bundle(
        client, admin_auth_headers, "Reorder Me",
        [_blank_q("R1"), _blank_q("R2"), _blank_q("R3")],
    )
    item_ids = [m["item_id"] for m in created["members"]]
    resp = await client.post(
        f"/api/onboarding/template-bundles/{created['id']}/reorder",
        headers=admin_auth_headers,
        json={"ordered_item_ids": list(reversed(item_ids))},
    )
    assert resp.status_code == 200, resp.text
    members = resp.json()["members"]
    assert [m["item_id"] for m in members] == list(reversed(item_ids))
    assert [m["display_order"] for m in members] == [0, 1, 2]


async def test_bundle_reorder_rejects_non_permutation_422(
    client, admin_auth_headers
):
    created = await _create_bundle(
        client, admin_auth_headers, "Reorder Bad", [_blank_q("X1"), _blank_q("X2")]
    )
    resp = await client.post(
        f"/api/onboarding/template-bundles/{created['id']}/reorder",
        headers=admin_auth_headers, json={"ordered_item_ids": [999999]},
    )
    assert resp.status_code == 422, resp.text


async def test_bundle_add_item(client, db_session, admin_auth_headers):
    extra = await _questionnaire(db_session, name="Extra Doc")
    await db_session.commit()
    created = await _create_bundle(
        client, admin_auth_headers, "Add Me", [_blank_q("A1")]
    )
    resp = await client.post(
        f"/api/onboarding/template-bundles/{created['id']}/items",
        headers=admin_auth_headers, json={"template_id": extra.id},
    )
    assert resp.status_code == 200, resp.text
    members = resp.json()["members"]
    assert members[-1]["template_id"] == extra.id
    assert members[-1]["display_order"] == 1


async def test_bundle_add_duplicate_template_422(
    client, db_session, admin_auth_headers
):
    extra = await _questionnaire(db_session, name="Dup Doc")
    await db_session.commit()
    created = await _create_bundle(
        client, admin_auth_headers, "Add Dup", [_blank_q("D1")]
    )
    ok = await client.post(
        f"/api/onboarding/template-bundles/{created['id']}/items",
        headers=admin_auth_headers, json={"template_id": extra.id},
    )
    assert ok.status_code == 200
    again = await client.post(
        f"/api/onboarding/template-bundles/{created['id']}/items",
        headers=admin_auth_headers, json={"template_id": extra.id},
    )
    assert again.status_code == 422, again.text


async def test_bundle_remove_item(client, admin_auth_headers):
    created = await _create_bundle(
        client, admin_auth_headers, "Remove Me", [_blank_q("M1"), _blank_q("M2")]
    )
    item_id = created["members"][0]["item_id"]
    resp = await client.delete(
        f"/api/onboarding/template-bundles/{created['id']}/items/{item_id}",
        headers=admin_auth_headers,
    )
    assert resp.status_code == 204, resp.text
    detail = await client.get(
        f"/api/onboarding/template-bundles/{created['id']}",
        headers=admin_auth_headers,
    )
    assert [m["item_id"] for m in detail.json()["members"]] == [
        created["members"][1]["item_id"]
    ]


async def test_bundle_remove_last_item_422(client, admin_auth_headers):
    created = await _create_bundle(
        client, admin_auth_headers, "Last One", [_blank_q("Solo")]
    )
    item_id = created["members"][0]["item_id"]
    resp = await client.delete(
        f"/api/onboarding/template-bundles/{created['id']}/items/{item_id}",
        headers=admin_auth_headers,
    )
    assert resp.status_code == 422, resp.text


async def test_bundle_update_rename_and_retire(client, admin_auth_headers):
    created = await _create_bundle(
        client, admin_auth_headers, "Old Name", [_blank_q("U1")]
    )
    resp = await client.patch(
        f"/api/onboarding/template-bundles/{created['id']}",
        headers=admin_auth_headers, json={"name": "New Name", "is_active": False},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "New Name"
    assert resp.json()["is_active"] is False


async def test_bundle_delete(client, db_session, admin_auth_headers):
    created = await _create_bundle(
        client, admin_auth_headers, "Delete Me", [_blank_q("X")]
    )
    resp = await client.delete(
        f"/api/onboarding/template-bundles/{created['id']}",
        headers=admin_auth_headers,
    )
    assert resp.status_code == 204, resp.text
    gone = (
        await db_session.execute(
            select(OnboardingTemplateBundle).where(
                OnboardingTemplateBundle.id == created["id"]
            )
        )
    ).scalar_one_or_none()
    assert gone is None


async def test_bundle_create_perm_403(client, viewer_auth_headers):
    resp = await client.post(
        "/api/onboarding/template-bundles",
        headers=viewer_auth_headers,
        json={"name": "Nope", "items": [_blank_q("N1")]},
    )
    assert resp.status_code == 403, resp.text


async def test_bundle_send_ready_false_for_retired_member(
    client, db_session, admin_auth_headers
):
    created = await _create_bundle(
        client, admin_auth_headers, "Has Retiree", [_blank_q("RM1"), _blank_q("RM2")]
    )
    # Retire one member's template directly, then re-read the detail.
    tid = created["members"][0]["template_id"]
    template = (
        await db_session.execute(
            select(OnboardingTemplate).where(OnboardingTemplate.id == tid)
        )
    ).scalar_one()
    template.is_active = False
    await db_session.commit()

    detail = await client.get(
        f"/api/onboarding/template-bundles/{created['id']}",
        headers=admin_auth_headers,
    )
    body = detail.json()
    assert body["send_ready"] is False
    retired = next(m for m in body["members"] if m["template_id"] == tid)
    assert retired["send_ready"] is False
    assert retired["is_active"] is False


# ===========================================================================
# Send-from-bundle (§4.7) — re-validation via the existing packet create path
# ===========================================================================
async def test_send_from_bundle_preserves_order(db_session, test_contact):
    """The bundle detail's ordered template_ids mint packet docs in that order."""
    t1 = await make_template(db_session, name="Send1")
    t2 = await make_template(db_session, name="Send2")
    t3 = await make_template(db_session, name="Send3")
    bundle = OnboardingTemplateBundle(name="Send Bundle")
    db_session.add(bundle)
    await db_session.flush()
    for order, t in enumerate([t3, t1, t2]):
        db_session.add(OnboardingTemplateBundleItem(
            bundle_id=bundle.id, template_id=t.id, display_order=order))
    await db_session.flush()

    _b, members, _ready = await BundleService(db_session).get_bundle_detail(bundle.id)
    ordered_ids = [m.template_id for m in members]
    assert ordered_ids == [t3.id, t1.id, t2.id]

    packet, _raw = await PacketService(db_session).create_packet(
        created_by_id=None, contact_id=test_contact.id,
        recipient_email="client@example.com", template_ids=ordered_ids,
    )
    docs = await PacketService(db_session).load_documents(packet.id)
    assert [d.source_template_id for d in docs] == [t3.id, t1.id, t2.id]


async def test_send_blocked_when_member_not_ready_and_named(
    db_session, test_contact
):
    """A member retired between preselect and send is BLOCKED (not skipped) and
    named explicitly — the TOCTOU re-validation via template_send_status."""
    good = await make_template(db_session, name="GoodSend")
    retired = await make_template(db_session, name="RetiredSend", is_active=False)
    svc = PacketService(db_session)
    with pytest.raises(PacketValidationError, match=f"Template {retired.id}"):
        await svc.create_packet(
            created_by_id=None, contact_id=test_contact.id,
            recipient_email="client@example.com",
            template_ids=[good.id, retired.id],
        )


# ===========================================================================
# V3-3 regression: selection readiness routes through template_send_status
# ===========================================================================
async def test_selection_allows_no_pdf_questionnaire(db_session, test_user):
    """A no-PDF questionnaire is selectable (needs_pdf_copy is False) — proves
    the kind-gated readiness via the shared template_send_status."""
    proposal = Proposal(
        proposal_number=f"PR-{uuid.uuid4().hex[:6]}", title="P", status="sent",
        owner_id=test_user.id, created_by_id=test_user.id,
    )
    db_session.add(proposal)
    await db_session.flush()
    q = await _questionnaire(db_session)
    rows = await SelectionService(db_session).set_selections(
        proposal.id, template_ids=[q.id], actor_id=test_user.id
    )
    assert [r.template_id for r in rows] == [q.id]


async def test_selection_rejects_no_pdf_esign_via_send_status(db_session, test_user):
    """A no-PDF esign template is still a 422 ("no PDF") through the shared check."""
    proposal = Proposal(
        proposal_number=f"PR-{uuid.uuid4().hex[:6]}", title="P", status="sent",
        owner_id=test_user.id, created_by_id=test_user.id,
    )
    db_session.add(proposal)
    await db_session.flush()
    esign = await _esign_no_pdf(db_session)
    with pytest.raises(PacketValidationError, match="no PDF"):
        await SelectionService(db_session).set_selections(
            proposal.id, template_ids=[esign.id], actor_id=test_user.id
        )

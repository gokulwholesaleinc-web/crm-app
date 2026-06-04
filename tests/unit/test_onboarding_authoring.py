"""No-mock tests for v3 template authoring (Phase 2 — create + PATCH per kind).

Proves the widened contract:
- POST /templates with kind=questionnaire/upload_request accepts initial
  field_definitions, validated by the per-kind handler (valid → 201; malformed
  → 422 from the handler, not the schema).
- POST /templates with kind=esign_pdf rejects initial field_definitions (coords
  are placed after a PDF upload).
- PATCH field_definitions round-trips for questionnaire + upload (valid → 200,
  stored; malformed → 422).
- The list[dict] widening did NOT drop esign field-SHAPE validation: a malformed
  esign field still 422s (the handler now re-validates against FieldDefinition),
  while a valid one saves.

Real SQLite + ASGI client through the staff routes; nothing mocked.
"""

import io

import pytest
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from src.onboarding import storage

pytestmark = pytest.mark.asyncio


def _pdf_bytes(text: str = "Onboarding form") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.drawString(72, 720, text)
    c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _sweep_onboarding_uploads():
    """Remove any onboarding files created during a test (disk branch)."""
    root = storage.ONBOARDING_DIR

    def _snapshot() -> set:
        return set(root.rglob("*")) if root.exists() else set()

    before = _snapshot()
    yield
    after = _snapshot()
    for path in sorted(after - before, key=lambda p: len(str(p)), reverse=True):
        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        except OSError:
            pass


async def _create(client, headers, **body):
    return await client.post(
        "/api/onboarding/templates", json={"name": "T", **body}, headers=headers
    )


async def _upload(client, headers, template_id):
    return await client.post(
        f"/api/onboarding/templates/{template_id}/pdf",
        files={"file": ("t.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")},
        headers=headers,
    )


# Valid per-kind field definitions.
_QUESTION = {"id": "q_name", "kind": "short_text", "label": "Full name", "required": True}
_CHOICE = {
    "id": "q_color",
    "kind": "single_choice",
    "label": "Favorite color",
    "required": True,
    "options": [{"value": "r", "label": "Red"}, {"value": "b", "label": "Blue"}],
}
_FILE = {"id": "u_id", "kind": "file_upload", "label": "Gov ID", "required": True,
         "maxFiles": 2, "maxMB": 10}
_ESIGN_SIG = {"id": "f_sig", "kind": "signature", "label": "Signature",
              "required": True, "prefill": None, "page": 1,
              "x": 72.0, "y": 200.0, "w": 220.0, "h": 60.0}


# --------------------------------------------------------------------------
# Create with kind + initial fields
# --------------------------------------------------------------------------


async def test_create_questionnaire_with_initial_fields(client, auth_headers):
    resp = await _create(
        client, auth_headers, kind="questionnaire",
        field_definitions=[_QUESTION, _CHOICE],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "questionnaire"
    assert [f["id"] for f in body["field_definitions"]] == ["q_name", "q_color"]
    assert body["has_pdf"] is False


async def test_create_upload_with_initial_fields(client, auth_headers):
    resp = await _create(
        client, auth_headers, kind="upload_request", field_definitions=[_FILE],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "upload_request"
    assert body["field_definitions"][0]["maxFiles"] == 2


async def test_create_esign_rejects_initial_fields(client, auth_headers):
    """esign_pdf places coords after a PDF upload — initial fields are 422."""
    resp = await _create(
        client, auth_headers, kind="esign_pdf", field_definitions=[_ESIGN_SIG],
    )
    assert resp.status_code == 422, resp.text


async def test_create_defaults_to_esign_pdf(client, auth_headers):
    """Omitting kind keeps the pre-v3 default (back-compat)."""
    resp = await _create(client, auth_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["kind"] == "esign_pdf"


async def test_create_questionnaire_malformed_fields_422(client, auth_headers):
    """A choice field with no options is rejected by the per-kind validator."""
    bad = {"id": "q_bad", "kind": "single_choice", "label": "Bad", "required": True}
    resp = await _create(
        client, auth_headers, kind="questionnaire", field_definitions=[bad],
    )
    assert resp.status_code == 422, resp.text


# --------------------------------------------------------------------------
# PATCH round-trips (questionnaire + upload)
# --------------------------------------------------------------------------


async def test_patch_questionnaire_roundtrip(client, auth_headers):
    created = await _create(client, auth_headers, kind="questionnaire")
    tid = created.json()["id"]

    ok = await client.patch(
        f"/api/onboarding/templates/{tid}",
        json={"field_definitions": [_QUESTION, _CHOICE]},
        headers=auth_headers,
    )
    assert ok.status_code == 200, ok.text
    assert [f["id"] for f in ok.json()["field_definitions"]] == ["q_name", "q_color"]

    # allow_other on a text field is a per-kind definition error → 422.
    bad = await client.patch(
        f"/api/onboarding/templates/{tid}",
        json={"field_definitions": [{**_QUESTION, "allow_other": True}]},
        headers=auth_headers,
    )
    assert bad.status_code == 422, bad.text


async def test_patch_upload_roundtrip(client, auth_headers):
    created = await _create(client, auth_headers, kind="upload_request")
    tid = created.json()["id"]

    ok = await client.patch(
        f"/api/onboarding/templates/{tid}",
        json={"field_definitions": [_FILE]},
        headers=auth_headers,
    )
    assert ok.status_code == 200, ok.text

    # maxFiles must be a positive int within the ceiling.
    bad = await client.patch(
        f"/api/onboarding/templates/{tid}",
        json={"field_definitions": [{**_FILE, "maxFiles": 0}]},
        headers=auth_headers,
    )
    assert bad.status_code == 422, bad.text


# --------------------------------------------------------------------------
# Widening did NOT drop esign field-shape validation
# --------------------------------------------------------------------------


async def test_patch_esign_dict_still_validates_shape(client, auth_headers):
    created = await _create(client, auth_headers, kind="esign_pdf")
    tid = created.json()["id"]
    up = await _upload(client, auth_headers, tid)
    assert up.status_code == 200, up.text

    # A malformed esign field (bad kind enum) must still 422 even though the
    # request now carries raw dicts — the handler re-validates the shape.
    bad = await client.patch(
        f"/api/onboarding/templates/{tid}",
        json={"field_definitions": [{**_ESIGN_SIG, "kind": "bogus"}]},
        headers=auth_headers,
    )
    assert bad.status_code == 422, bad.text

    # A valid esign field still saves.
    ok = await client.patch(
        f"/api/onboarding/templates/{tid}",
        json={"field_definitions": [_ESIGN_SIG]},
        headers=auth_headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["field_definitions"][0]["id"] == "f_sig"


async def test_patch_esign_stores_normalized_field_shape(client, auth_headers):
    """list[dict] still persists the NORMALIZED esign shape: a string 'no'
    becomes a real bool and undeclared keys are dropped (the guarantee the old
    list[FieldDefinition] request type gave for free)."""
    created = await _create(client, auth_headers, kind="esign_pdf")
    tid = created.json()["id"]
    up = await _upload(client, auth_headers, tid)
    assert up.status_code == 200, up.text

    messy = {**_ESIGN_SIG, "kind": "text", "required": "no", "junk": "x"}
    resp = await client.patch(
        f"/api/onboarding/templates/{tid}",
        json={"field_definitions": [messy]},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    stored = resp.json()["field_definitions"][0]
    assert stored["required"] is False  # coerced from "no" to a real bool
    assert "junk" not in stored          # undeclared key dropped


async def test_create_duplicate_name_does_not_poison_session(client, auth_headers):
    """A duplicate-name 422 rolls back cleanly — a follow-up create succeeds."""
    first = await _create(client, auth_headers, kind="questionnaire", name="Intake")
    assert first.status_code == 201, first.text
    dup = await _create(client, auth_headers, kind="questionnaire", name="Intake")
    assert dup.status_code == 422, dup.text
    third = await _create(client, auth_headers, kind="questionnaire", name="Intake 2")
    assert third.status_code == 201, third.text


async def test_create_questionnaire_requires_esign_true_422(client, auth_headers):
    """requires_esign can't be set at create for any kind (#10)."""
    resp = await _create(
        client, auth_headers, kind="questionnaire", requires_esign=True,
    )
    assert resp.status_code == 422, resp.text

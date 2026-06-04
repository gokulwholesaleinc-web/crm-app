"""No-mock tests for onboarding template CRUD endpoints (build-order §C).

Every endpoint/method gets ≥1 real-HTTP test through the ``client`` fixture
against the in-memory SQLite DB — nothing is mocked. Uploaded PDFs land on
local disk (R2 creds absent → disk branch); an autouse fixture sweeps the
onboarding upload dir between tests so they stay hermetic.

Coordinate-bounds assertions use a LETTER (612×792 pt) PDF built in-test with
reportlab so the in-bounds / out-of-bounds boundaries are deterministic.
"""

import io

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.onboarding import storage
from src.onboarding.models import OnboardingTemplate
from src.roles.models import Role, UserRole

# --- in-test PDF builder (no fixtures, no mocks) ---------------------------


def _pdf_bytes(pages: int = 1) -> bytes:
    """A valid multi-page LETTER PDF (known 612x792 page size)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    for i in range(pages):
        c.drawString(72, 720, f"Onboarding page {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def _encrypted_pdf_bytes(password: str = "secret") -> bytes:
    """A real password-encrypted PDF (built with pypdf, no mocks)."""
    reader = PdfReader(io.BytesIO(_pdf_bytes()))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _rotated_pdf_bytes(degrees: int = 90) -> bytes:
    """A valid PDF whose single page carries a non-zero /Rotate."""
    reader = PdfReader(io.BytesIO(_pdf_bytes()))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.pages[0].rotate(degrees)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _field(**overrides) -> dict:
    """A valid, in-bounds field definition; override individual keys."""
    base = {
        "id": "f_ein",
        "kind": "text",
        "label": "Federal EIN",
        "required": False,
        "prefill": None,
        "page": 1,
        "x": 72.0,
        "y": 144.0,
        "w": 180.0,
        "h": 24.0,
    }
    base.update(overrides)
    return base


# --- autouse disk sweep so upload tests don't leak files -------------------


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


# --- helpers ---------------------------------------------------------------


async def _create_template(client, headers, **body) -> dict:
    payload = {"name": "Service Agreement", **body}
    resp = await client.post(
        "/api/onboarding/templates", json=payload, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _upload_pdf(client, headers, template_id: int, pdf: bytes | None = None):
    pdf = pdf if pdf is not None else _pdf_bytes()
    return await client.post(
        f"/api/onboarding/templates/{template_id}/pdf",
        files={"file": ("template.pdf", io.BytesIO(pdf), "application/pdf")},
        headers=headers,
    )


async def _make_esign_template(client, headers, **body) -> dict:
    """Build a requires_esign template the only way the API allows it.

    Create rejects requires_esign at create (#10, _no_esign_at_create), so the
    real flow is: create (esign off) → upload PDF → PATCH a signature field
    AND requires_esign=true together (schema half passes, service reconciles).
    Returns the PATCH response body (requires_esign True, one signature field).
    """
    tmpl = await _create_template(client, headers, **body)
    up = await _upload_pdf(client, headers, tmpl["id"])
    assert up.status_code == 200, up.text
    patch = await client.patch(
        f"/api/onboarding/templates/{tmpl['id']}",
        json={
            "requires_esign": True,
            "field_definitions": [
                _field(id="f_sig", kind="signature", label="Signature"),
            ],
        },
        headers=headers,
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["requires_esign"] is True
    return body


@pytest.fixture
async def no_read_perm_headers(db_session) -> dict:
    """Auth headers for a REAL user whose role grants no ``contacts`` perm.

    No mocks: we persist a ``Role`` with an explicit empty permission matrix
    (``{}``) and bind it to a fresh, non-superuser ``User`` via a real
    ``UserRole`` row. ``RoleService.get_user_permissions`` returns ``{}`` for
    this user, so ``require_permission("contacts","read")`` denies → 403. This
    proves the onboarding reads are permission-gated, not bare-authenticated.
    """
    role = Role(
        name="onb-no-perm",
        description="Locked-down role with no entity permissions",
        permissions={},
    )
    db_session.add(role)
    await db_session.flush()

    user = User(
        email="onb_noperm@example.com",
        hashed_password=get_password_hash("noperm-password123"),
        full_name="No-Perm User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    await db_session.commit()

    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# POST /templates
# =============================================================================


class TestCreateTemplate:
    @pytest.mark.asyncio
    async def test_create_returns_201_with_audit_and_defaults(
        self, client, auth_headers, test_user
    ):
        """POST /templates → 201; owner/creator set, defaults applied."""
        resp = await client.post(
            "/api/onboarding/templates",
            json={"name": "Vendor Setup", "service_tag": "vendor"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["owner_id"] == test_user.id
        # #3 SECURITY (C1): never expose the raw storage ref; has_pdf instead.
        assert "pdf_path" not in body
        assert body["has_pdf"] is False
        assert body["pdf_version"] == 1
        assert body["field_definitions"] == []
        assert body["is_active"] is True
        assert body["service_tag"] == "vendor"

    @pytest.mark.asyncio
    async def test_create_requires_auth(self, client):
        """Unauthenticated create → 401."""
        resp = await client.post(
            "/api/onboarding/templates", json={"name": "Nope"}
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_rejects_blank_name(self, client, auth_headers):
        """Empty name → 422 (Pydantic min_length)."""
        resp = await client.post(
            "/api/onboarding/templates", json={"name": ""}, headers=auth_headers
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_with_requires_esign_true_422(self, client, auth_headers):
        """#10 (TemplateCreate._no_esign_at_create): a brand-new template has
        no fields yet, so requires_esign=true at create → 422.

        e-sign is enabled later via PATCH once a signature field exists; the
        invariant can't be satisfied at create time.
        """
        resp = await client.post(
            "/api/onboarding/templates",
            json={"name": "Esign At Create", "requires_esign": True},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("esign_payload", [{"requires_esign": False}, {}])
    async def test_create_with_esign_false_or_omitted_201(
        self, client, auth_headers, esign_payload
    ):
        """#10: requires_esign=false (or omitted → default false) → 201."""
        resp = await client.post(
            "/api/onboarding/templates",
            json={"name": "No Esign", **esign_payload},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["requires_esign"] is False

    @pytest.mark.asyncio
    async def test_create_duplicate_name_422(self, client, auth_headers):
        """S1: a second template with the same name → clean 422 (not a 500).

        The unique constraint ``uq_onboarding_templates_name`` (created by
        ``Base.metadata.create_all`` on the SQLite test DB) raises an
        IntegrityError that ``service.create`` translates to
        ``DuplicateTemplateNameError`` → 422. No duplicate row is created.
        """
        first = await client.post(
            "/api/onboarding/templates",
            json={"name": "Strategy Intake"},
            headers=auth_headers,
        )
        assert first.status_code == 201, first.text

        dup = await client.post(
            "/api/onboarding/templates",
            json={"name": "Strategy Intake"},
            headers=auth_headers,
        )
        assert dup.status_code == 422, dup.text
        assert "already exists" in dup.json()["detail"].lower()

        # The session is still usable after the rolled-back collision — a
        # differently-named create still succeeds.
        ok = await client.post(
            "/api/onboarding/templates",
            json={"name": "Strategy Intake 2"},
            headers=auth_headers,
        )
        assert ok.status_code == 201, ok.text


# =============================================================================
# GET /templates  (global team library)
# =============================================================================


class TestListTemplates:
    @pytest.mark.asyncio
    async def test_list_is_global_across_owners(
        self, client, auth_headers, admin_auth_headers
    ):
        """A template owned by admin is visible to a different user (no owner filter)."""
        created = await _create_template(
            client, admin_auth_headers, name="Admin-owned"
        )
        resp = await client.get("/api/onboarding/templates", headers=auth_headers)
        assert resp.status_code == 200
        ids = [t["id"] for t in resp.json()]
        assert created["id"] in ids

    @pytest.mark.asyncio
    async def test_list_filters_by_service_tag(self, client, auth_headers):
        """?service_tag filters the library."""
        a = await _create_template(client, auth_headers, name="A", service_tag="legal")
        await _create_template(client, auth_headers, name="B", service_tag="finance")
        resp = await client.get(
            "/api/onboarding/templates?service_tag=legal", headers=auth_headers
        )
        assert resp.status_code == 200
        tags = {t["service_tag"] for t in resp.json()}
        assert tags == {"legal"}
        ids = [t["id"] for t in resp.json()]
        assert a["id"] in ids

    @pytest.mark.asyncio
    async def test_include_inactive_toggle(self, client, auth_headers):
        """Retired rows hidden by default, shown with include_inactive=true."""
        tmpl = await _create_template(client, auth_headers, name="ToRetire")
        await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/retire", headers=auth_headers
        )

        default = await client.get("/api/onboarding/templates", headers=auth_headers)
        assert tmpl["id"] not in [t["id"] for t in default.json()]

        with_inactive = await client.get(
            "/api/onboarding/templates?include_inactive=true", headers=auth_headers
        )
        assert tmpl["id"] in [t["id"] for t in with_inactive.json()]

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, client):
        """Unauthenticated list → 401."""
        resp = await client.get("/api/onboarding/templates")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_serializes_non_esign_kinds(
        self, client, auth_headers, db_session
    ):
        """Regression: questionnaire / upload_request templates carry non-
        coordinate field_definitions, so forcing them through the esign
        ``FieldDefinition`` model 500s the list (it did, for the seeded Google
        Forms). The response must pass field_definitions through as raw dicts
        and surface the ``kind`` discriminator instead."""
        questionnaire = OnboardingTemplate(
            name="Seeded questionnaire",
            kind="questionnaire",
            field_definitions=[
                {
                    "id": "full_name",
                    "kind": "short_text",
                    "label": "Full name",
                    "required": True,
                },
                {
                    "id": "interests",
                    "kind": "multi_choice",
                    "label": "Interests",
                    "options": [{"value": "a", "label": "A"}],
                    "required": False,
                },
            ],
        )
        upload = OnboardingTemplate(
            name="Seeded upload request",
            kind="upload_request",
            field_definitions=[
                {
                    "id": "logo",
                    "kind": "file_upload",
                    "label": "Logo",
                    "maxFiles": 1,
                    "maxMB": 10,
                }
            ],
        )
        db_session.add_all([questionnaire, upload])
        await db_session.commit()

        resp = await client.get("/api/onboarding/templates", headers=auth_headers)
        assert resp.status_code == 200
        by_name = {t["name"]: t for t in resp.json()}

        q = by_name["Seeded questionnaire"]
        assert q["kind"] == "questionnaire"
        assert q["has_pdf"] is False
        assert q["field_definitions"][0]["kind"] == "short_text"
        assert q["field_definitions"][1]["kind"] == "multi_choice"

        u = by_name["Seeded upload request"]
        assert u["kind"] == "upload_request"
        assert u["field_definitions"][0]["kind"] == "file_upload"

    @pytest.mark.asyncio
    async def test_create_exposes_esign_pdf_kind_default(self, client, auth_headers):
        """A template created via the API defaults to the esign_pdf kind, and
        the response now surfaces that discriminator."""
        created = await _create_template(client, auth_headers, name="Default kind")
        assert created["kind"] == "esign_pdf"


# =============================================================================
# GET /templates/{id}
# =============================================================================


class TestGetTemplate:
    @pytest.mark.asyncio
    async def test_get_existing(self, client, auth_headers):
        """GET by id → 200 with the row."""
        tmpl = await _create_template(client, auth_headers, name="Detail")
        resp = await client.get(
            f"/api/onboarding/templates/{tmpl['id']}", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == tmpl["id"]

    @pytest.mark.asyncio
    async def test_get_missing_404(self, client, auth_headers):
        """GET unknown id → 404."""
        resp = await client.get(
            "/api/onboarding/templates/999999", headers=auth_headers
        )
        assert resp.status_code == 404


# =============================================================================
# POST /templates/{id}/pdf
# =============================================================================


class TestUploadPdf:
    @pytest.mark.asyncio
    async def test_upload_sets_pdf_path(self, client, auth_headers):
        """Upload → 200, has_pdf True, version stays 1 on first upload."""
        tmpl = await _create_template(client, auth_headers, name="Upload")
        resp = await _upload_pdf(client, auth_headers, tmpl["id"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # #3 (C1): no raw pdf_path leaks; has_pdf flips to True after upload.
        assert "pdf_path" not in body
        assert body["has_pdf"] is True
        assert body["pdf_version"] == 1

    @pytest.mark.asyncio
    async def test_upload_non_pdf_400(self, client, auth_headers):
        """Non-PDF bytes → 400 (unreadable PDF)."""
        tmpl = await _create_template(client, auth_headers, name="BadUpload")
        resp = await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/pdf",
            files={"file": ("notes.txt", io.BytesIO(b"hello world"), "text/plain")},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_encrypted_pdf_400(self, client, auth_headers):
        """#4: an encrypted/password-protected PDF → 400, nothing stored."""
        tmpl = await _create_template(client, auth_headers, name="EncUpload")
        resp = await _upload_pdf(
            client, auth_headers, tmpl["id"], _encrypted_pdf_bytes()
        )
        assert resp.status_code == 400, resp.text
        assert "ncrypted" in resp.json()["detail"]
        # Rejected pre-write: the row still has no PDF.
        got = await client.get(
            f"/api/onboarding/templates/{tmpl['id']}", headers=auth_headers
        )
        assert got.json()["has_pdf"] is False

    @pytest.mark.asyncio
    async def test_upload_rotated_pdf_400(self, client, auth_headers):
        """#8: a page with a non-zero /Rotate → 400 (would misplace fields)."""
        tmpl = await _create_template(client, auth_headers, name="RotUpload")
        resp = await _upload_pdf(
            client, auth_headers, tmpl["id"], _rotated_pdf_bytes(90)
        )
        assert resp.status_code == 400, resp.text
        assert "otated" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_missing_template_404(self, client, auth_headers):
        """Upload to unknown template → 404."""
        resp = await _upload_pdf(client, auth_headers, 999999)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_check_ownership_403(
        self, client, sales_rep_auth_headers, auth_headers
    ):
        """Different non-admin uploading another user's template → 403."""
        tmpl = await _create_template(
            client, sales_rep_auth_headers, name="OwnedBySalesRep"
        )
        resp = await _upload_pdf(client, auth_headers, tmpl["id"])
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_upload_admin_bypasses_ownership(
        self, client, sales_rep_auth_headers, admin_auth_headers
    ):
        """Admin can upload to a template it does not own (check_ownership bypass)."""
        tmpl = await _create_template(
            client, sales_rep_auth_headers, name="OwnedBySalesRep2"
        )
        resp = await _upload_pdf(client, admin_auth_headers, tmpl["id"])
        assert resp.status_code == 200, resp.text

    @pytest.mark.asyncio
    async def test_reupload_bumps_version_and_clears_fields(
        self, client, auth_headers
    ):
        """Re-upload → pdf_version 1→2 AND field_definitions cleared to []."""
        tmpl = await _create_template(client, auth_headers, name="Reupload")
        await _upload_pdf(client, auth_headers, tmpl["id"])

        # Set some fields first via PATCH.
        patch = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"field_definitions": [_field()]},
            headers=auth_headers,
        )
        assert patch.status_code == 200, patch.text
        assert len(patch.json()["field_definitions"]) == 1

        # Re-upload a fresh PDF.
        resp = await _upload_pdf(client, auth_headers, tmpl["id"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["pdf_version"] == 2
        assert body["field_definitions"] == []

    @pytest.mark.asyncio
    async def test_reupload_clears_requires_esign(self, client, auth_headers):
        """#10 (service.upload_pdf): re-upload turns requires_esign back OFF.

        Old coords (incl. the signature field) are meaningless against the new
        PDF, so re-upload clears field_definitions; leaving requires_esign on
        with zero signature fields would violate the #10 invariant, so the
        service resets it too. Staff re-enable esign after re-placing a sig.
        """
        esign = await _make_esign_template(client, auth_headers, name="EsignReupload")
        tmpl_id = esign["id"]
        assert esign["requires_esign"] is True
        assert len(esign["field_definitions"]) == 1

        # Re-upload a 2nd PDF → fields cleared AND requires_esign reset.
        resp = await _upload_pdf(client, auth_headers, tmpl_id)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["requires_esign"] is False
        assert body["field_definitions"] == []

        # GET reflects the same reset (not just the upload response).
        got = await client.get(
            f"/api/onboarding/templates/{tmpl_id}", headers=auth_headers
        )
        assert got.json()["requires_esign"] is False
        assert got.json()["field_definitions"] == []


# =============================================================================
# PATCH /templates/{id}
# =============================================================================


class TestPatchTemplate:
    @pytest.mark.asyncio
    async def test_patch_metadata(self, client, auth_headers):
        """PATCH plain metadata fields → 200 with new values.

        ``requires_esign`` is NOT toggled here: #10 forbids turning it on
        without a signature field, so that path has its own tests below.
        """
        tmpl = await _create_template(client, auth_headers, name="Old")
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"name": "New Name", "description": "Updated copy"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "New Name"
        assert body["description"] == "Updated copy"
        assert body["requires_esign"] is False

    @pytest.mark.asyncio
    async def test_patch_valid_field_definitions(self, client, auth_headers):
        """In-bounds field_definitions → 200."""
        tmpl = await _create_template(client, auth_headers, name="Fields")
        await _upload_pdf(client, auth_headers, tmpl["id"])
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={
                "field_definitions": [
                    _field(id="f_sig", kind="signature", label="Signature"),
                    _field(id="f_date", kind="date", label="Date", y=200.0),
                ]
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["field_definitions"]) == 2

    @pytest.mark.asyncio
    async def test_patch_fields_before_pdf_422(self, client, auth_headers):
        """field_definitions PATCH before any PDF uploaded → 422."""
        tmpl = await _create_template(client, auth_headers, name="NoPdf")
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"field_definitions": [_field()]},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_page_out_of_range_422(self, client, auth_headers):
        """page beyond the PDF's page count → 422 (service bounds check)."""
        tmpl = await _create_template(client, auth_headers, name="PageOOB")
        await _upload_pdf(client, auth_headers, tmpl["id"], _pdf_bytes(pages=1))
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"field_definitions": [_field(page=5)]},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_nonpositive_width_422(self, client, auth_headers):
        """w <= 0 → 422."""
        tmpl = await _create_template(client, auth_headers, name="WZero")
        await _upload_pdf(client, auth_headers, tmpl["id"])
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"field_definitions": [_field(w=0.0)]},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_box_out_of_bounds_422(self, client, auth_headers):
        """x + w beyond page width → 422."""
        tmpl = await _create_template(client, auth_headers, name="BoxOOB")
        await _upload_pdf(client, auth_headers, tmpl["id"])
        # x + w = 600 + 100 = 700 > 612 page width.
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"field_definitions": [_field(x=600.0, w=100.0)]},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_duplicate_field_id_422(self, client, auth_headers):
        """Duplicate field id within the doc → 422."""
        tmpl = await _create_template(client, auth_headers, name="DupId")
        await _upload_pdf(client, auth_headers, tmpl["id"])
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={
                "field_definitions": [
                    _field(id="f_dup", y=100.0),
                    _field(id="f_dup", y=300.0),
                ]
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_non_finite_coord_422(self, client, auth_headers):
        """Non-finite coordinate (NaN/Infinity) → 422."""
        tmpl = await _create_template(client, auth_headers, name="NonFinite")
        await _upload_pdf(client, auth_headers, tmpl["id"])
        # JSON has no NaN literal; httpx serializes float('inf') as Infinity,
        # which our service rejects via math.isfinite. Send raw to be explicit.
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            content=(
                '{"field_definitions": [{"id": "f_nan", "kind": "text", '
                '"label": "X", "page": 1, "x": 10.0, "y": 10.0, "w": 50.0, '
                '"h": Infinity}]}'
            ),
            headers={**auth_headers, "Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_bad_enum_kind_422(self, client, auth_headers):
        """Invalid field kind (Pydantic literal) → 422."""
        tmpl = await _create_template(client, auth_headers, name="BadKind")
        await _upload_pdf(client, auth_headers, tmpl["id"])
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"field_definitions": [_field(kind="checkbox")]},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_bad_slug_422(self, client, auth_headers):
        """Field id not matching ^[a-z0-9_]+$ → 422 (Pydantic pattern)."""
        tmpl = await _create_template(client, auth_headers, name="BadSlug")
        await _upload_pdf(client, auth_headers, tmpl["id"])
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"field_definitions": [_field(id="F EIN!")]},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_bad_prefill_422(self, client, auth_headers):
        """Disallowed prefill literal (contact.email) → 422 (Pydantic)."""
        tmpl = await _create_template(client, auth_headers, name="BadPrefill")
        await _upload_pdf(client, auth_headers, tmpl["id"])
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"field_definitions": [_field(prefill="contact.email")]},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_check_ownership_403(
        self, client, sales_rep_auth_headers, auth_headers
    ):
        """Different non-admin patching another user's template → 403."""
        tmpl = await _create_template(
            client, sales_rep_auth_headers, name="PatchOwned"
        )
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"name": "Hijacked"},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_patch_admin_bypasses_ownership(
        self, client, sales_rep_auth_headers, admin_auth_headers
    ):
        """Admin can patch a template it does not own."""
        tmpl = await _create_template(
            client, sales_rep_auth_headers, name="PatchOwned2"
        )
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"name": "Admin Edit"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Admin Edit"

    @pytest.mark.asyncio
    async def test_patch_missing_template_404(self, client, auth_headers):
        """PATCH unknown template → 404."""
        resp = await client.patch(
            "/api/onboarding/templates/999999",
            json={"name": "X"},
            headers=auth_headers,
        )
        assert resp.status_code == 404


# =============================================================================
# GET /templates/{id}/pdf
# =============================================================================


class TestGetTemplatePdf:
    @pytest.mark.asyncio
    async def test_get_pdf_after_upload(self, client, auth_headers):
        """GET .../pdf → 200 application/pdf with the uploaded bytes."""
        pdf = _pdf_bytes()
        tmpl = await _create_template(client, auth_headers, name="PdfStream")
        await _upload_pdf(client, auth_headers, tmpl["id"], pdf)
        resp = await client.get(
            f"/api/onboarding/templates/{tmpl['id']}/pdf", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content == pdf

    @pytest.mark.asyncio
    async def test_get_pdf_when_none_404(self, client, auth_headers):
        """GET .../pdf before any upload → 404."""
        tmpl = await _create_template(client, auth_headers, name="NoPdfStream")
        resp = await client.get(
            f"/api/onboarding/templates/{tmpl['id']}/pdf", headers=auth_headers
        )
        assert resp.status_code == 404


# =============================================================================
# POST /templates/{id}/retire
# =============================================================================


class TestRetireTemplate:
    @pytest.mark.asyncio
    async def test_retire_sets_inactive(self, client, auth_headers):
        """Retire → 200, is_active False."""
        tmpl = await _create_template(client, auth_headers, name="Retire")
        resp = await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/retire", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_retire_check_ownership_403(
        self, client, sales_rep_auth_headers, auth_headers
    ):
        """Different non-admin retiring another user's template → 403."""
        tmpl = await _create_template(
            client, sales_rep_auth_headers, name="RetireOwned"
        )
        resp = await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/retire", headers=auth_headers
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_retire_missing_404(self, client, auth_headers):
        """Retire unknown template → 404."""
        resp = await client.post(
            "/api/onboarding/templates/999999/retire", headers=auth_headers
        )
        assert resp.status_code == 404


# =============================================================================
# POST /templates/{id}/restore  (un-retire; check_ownership-gated)
# =============================================================================


class TestRestoreTemplate:
    @pytest.mark.asyncio
    async def test_restore_sets_active(self, client, auth_headers):
        """Retire then restore → 200, is_active flips back to True."""
        tmpl = await _create_template(client, auth_headers, name="RestoreMe")
        retired = await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/retire", headers=auth_headers
        )
        assert retired.json()["is_active"] is False

        resp = await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/restore", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_active"] is True

    @pytest.mark.asyncio
    async def test_restore_unblocks_patch_that_409d_while_retired(
        self, client, auth_headers
    ):
        """A PATCH that 409'd on a retired template SUCCEEDS after restore (#11).

        Proves restore truly lifts the read-only guard, not just the flag:
        retire → PATCH 409 → restore → the same PATCH now 200s.
        """
        tmpl = await _create_template(client, auth_headers, name="RestoreUnblock")
        await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/retire", headers=auth_headers
        )

        blocked = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"name": "Edited While Retired"},
            headers=auth_headers,
        )
        assert blocked.status_code == 409, blocked.text

        restore = await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/restore", headers=auth_headers
        )
        assert restore.status_code == 200, restore.text

        ok = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"name": "Edited After Restore"},
            headers=auth_headers,
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["name"] == "Edited After Restore"

    @pytest.mark.asyncio
    async def test_restore_check_ownership_403(
        self, client, sales_rep_auth_headers, auth_headers
    ):
        """Different non-admin restoring another user's template → 403.

        Restore is check_ownership-gated just like retire.
        """
        tmpl = await _create_template(
            client, sales_rep_auth_headers, name="RestoreOwned"
        )
        await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/retire",
            headers=sales_rep_auth_headers,
        )
        resp = await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/restore", headers=auth_headers
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_restore_admin_bypasses_ownership(
        self, client, sales_rep_auth_headers, admin_auth_headers
    ):
        """Admin can restore a template it does not own (check_ownership bypass)."""
        tmpl = await _create_template(
            client, sales_rep_auth_headers, name="RestoreOwned2"
        )
        await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/retire",
            headers=sales_rep_auth_headers,
        )
        resp = await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/restore",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_active"] is True

    @pytest.mark.asyncio
    async def test_restore_missing_404(self, client, auth_headers):
        """Restore unknown template → 404."""
        resp = await client.post(
            "/api/onboarding/templates/999999/restore", headers=auth_headers
        )
        assert resp.status_code == 404


# =============================================================================
# #3 SECURITY — reads are permission-gated (contacts.read), not bare-auth
# =============================================================================


class TestReadPermissionGate:
    @pytest.mark.asyncio
    async def test_list_requires_contacts_read_permission(
        self, client, auth_headers, no_read_perm_headers
    ):
        """A user lacking contacts.read gets 403 on the global list (#3)."""
        await _create_template(client, auth_headers, name="GatedList")
        resp = await client.get(
            "/api/onboarding/templates", headers=no_read_perm_headers
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_requires_contacts_read_permission(
        self, client, auth_headers, no_read_perm_headers
    ):
        """A user lacking contacts.read gets 403 on GET by id (#3)."""
        tmpl = await _create_template(client, auth_headers, name="GatedGet")
        resp = await client.get(
            f"/api/onboarding/templates/{tmpl['id']}", headers=no_read_perm_headers
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_pdf_download_requires_contacts_read_permission(
        self, client, auth_headers, no_read_perm_headers
    ):
        """A user lacking contacts.read gets 403 on the PDF download (#3)."""
        tmpl = await _create_template(client, auth_headers, name="GatedPdf")
        await _upload_pdf(client, auth_headers, tmpl["id"])
        resp = await client.get(
            f"/api/onboarding/templates/{tmpl['id']}/pdf",
            headers=no_read_perm_headers,
        )
        assert resp.status_code == 403


# =============================================================================
# #6 service_tag slug validation / #7 whitespace name (Pydantic → 422)
# =============================================================================


class TestSchemaValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_tag", ["Vendor Setup", "UPPER", "has space", "   ", ""])
    async def test_create_rejects_bad_service_tag_422(
        self, client, auth_headers, bad_tag
    ):
        """#6: spaces/uppercase/empty service_tag → 422 (slug validator)."""
        resp = await client.post(
            "/api/onboarding/templates",
            json={"name": "Tagged", "service_tag": bad_tag},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_create_accepts_valid_service_tag_and_null(
        self, client, auth_headers
    ):
        """#6: a valid slug is accepted; null stays allowed (universal)."""
        ok = await client.post(
            "/api/onboarding/templates",
            json={"name": "Slugged", "service_tag": "vendor-setup-2"},
            headers=auth_headers,
        )
        assert ok.status_code == 201, ok.text
        assert ok.json()["service_tag"] == "vendor-setup-2"

        universal = await client.post(
            "/api/onboarding/templates",
            json={"name": "Universal", "service_tag": None},
            headers=auth_headers,
        )
        assert universal.status_code == 201, universal.text
        assert universal.json()["service_tag"] is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_tag", ["-", "--", "-x", "x-", "a--b"])
    async def test_create_rejects_bare_and_edge_hyphen_tags_422(
        self, client, auth_headers, bad_tag
    ):
        """#6 (_SERVICE_TAG_RE): bare/leading/trailing/doubled hyphens → 422.

        ``^[a-z0-9]+(?:-[a-z0-9]+)*$`` requires alnum segments joined by single
        hyphens, so '-', '--', '-x', 'x-', and 'a--b' are all rejected.
        """
        resp = await client.post(
            "/api/onboarding/templates",
            json={"name": "HyphenTag", "service_tag": bad_tag},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("good_tag", ["vendor-setup", "vendor", "abc123"])
    async def test_create_accepts_valid_hyphen_slugs_201(
        self, client, auth_headers, good_tag
    ):
        """#6 (_SERVICE_TAG_RE): well-formed slugs (incl. single-segment) → 201."""
        resp = await client.post(
            "/api/onboarding/templates",
            json={"name": "GoodTag", "service_tag": good_tag},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["service_tag"] == good_tag

    @pytest.mark.asyncio
    async def test_create_rejects_whitespace_only_name_422(
        self, client, auth_headers
    ):
        """#7: a name of only spaces → 422 (min_length alone allows '   ')."""
        resp = await client.post(
            "/api/onboarding/templates",
            json={"name": "   "},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_patch_rejects_bad_service_tag_422(self, client, auth_headers):
        """#6 on PATCH: an uppercase service_tag → 422."""
        tmpl = await _create_template(client, auth_headers, name="PatchTag")
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"service_tag": "Bad Tag"},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text


# =============================================================================
# #10 requires_esign ⇄ signature-field consistency (422)
# =============================================================================


class TestEsignSignatureConsistency:
    @pytest.mark.asyncio
    async def test_patch_esign_template_to_sig_less_fields_422(
        self, client, auth_headers
    ):
        """#10 (merged-state): an esign template PATCHed to a sig-less field
        set → 422.

        Create rejects requires_esign at create now (_no_esign_at_create), so
        we build a proper esign template (sig field placed), then PATCH the
        field_definitions down to a text-only set. The service reconciles the
        merged state (requires_esign still True + zero signature fields) and
        rejects — proving the guard fires on a field-only PATCH too.
        """
        esign = await _make_esign_template(
            client, auth_headers, name="EsignToSigLess"
        )
        resp = await client.patch(
            f"/api/onboarding/templates/{esign['id']}",
            json={"field_definitions": [_field(id="f_text", kind="text")]},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_patch_turn_on_esign_without_sig_field_422(
        self, client, auth_headers
    ):
        """#10 (merged-state): toggling esign on with no sig field on the row → 422.

        The single PATCH carries no field_definitions, so the schema-half
        validator can't see them; the service reconciles against the row's
        persisted (empty) field set and rejects.
        """
        tmpl = await _create_template(client, auth_headers, name="ToggleEsign")
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"requires_esign": True},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_patch_esign_and_sig_field_same_payload_422(
        self, client, auth_headers
    ):
        """#10 (schema-half): esign-on + sig-less fields in ONE payload → 422."""
        tmpl = await _create_template(client, auth_headers, name="OnePayload")
        await _upload_pdf(client, auth_headers, tmpl["id"])
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={
                "requires_esign": True,
                "field_definitions": [_field(id="f_text", kind="text")],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text

    @pytest.mark.asyncio
    async def test_patch_esign_with_signature_field_ok(self, client, auth_headers):
        """#10 happy path: esign + a signature field together → 200."""
        tmpl = await _create_template(client, auth_headers, name="EsignWithSig")
        await _upload_pdf(client, auth_headers, tmpl["id"])
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={
                "requires_esign": True,
                "field_definitions": [
                    _field(id="f_sig", kind="signature", label="Sign here"),
                ],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["requires_esign"] is True
        assert len(body["field_definitions"]) == 1


# =============================================================================
# #11 retired templates are read-only (PATCH + POST /pdf → 409)
# =============================================================================


class TestRetiredTemplateEditsBlocked:
    @pytest.mark.asyncio
    async def test_patch_retired_template_409(self, client, auth_headers):
        """#11: PATCH on a retired template → 409 (restore first)."""
        tmpl = await _create_template(client, auth_headers, name="RetiredPatch")
        await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/retire", headers=auth_headers
        )
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"name": "Should Fail"},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert "retired" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_pdf_to_retired_template_409(self, client, auth_headers):
        """#11: POST /pdf on a retired template → 409."""
        tmpl = await _create_template(client, auth_headers, name="RetiredPdf")
        await client.post(
            f"/api/onboarding/templates/{tmpl['id']}/retire", headers=auth_headers
        )
        resp = await _upload_pdf(client, auth_headers, tmpl["id"])
        assert resp.status_code == 409, resp.text
        assert "retired" in resp.json()["detail"].lower()


# =============================================================================
# #2 (C2) optimistic lock — stale pdf_version on a field-save PATCH → 409
# =============================================================================


class TestStalePdfVersionLock:
    @pytest.mark.asyncio
    async def test_stale_pdf_version_field_save_409(self, client, auth_headers):
        """#2 (C2): a field PATCH carrying an out-of-date pdf_version → 409.

        Open the editor at pdf_version=1, re-upload (bumps to 2), then submit
        fields tagged pdf_version=1 → the coords reference a replaced PDF.
        """
        tmpl = await _create_template(client, auth_headers, name="StaleLock")
        first = await _upload_pdf(client, auth_headers, tmpl["id"])
        opened_version = first.json()["pdf_version"]
        assert opened_version == 1

        # Someone re-uploads underneath the open editor → version 2.
        reup = await _upload_pdf(client, auth_headers, tmpl["id"])
        assert reup.json()["pdf_version"] == 2

        # The editor saves fields still tagged with the stale version 1.
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={
                "field_definitions": [_field()],
                "pdf_version": opened_version,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert "replaced" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_matching_pdf_version_field_save_ok(self, client, auth_headers):
        """#2 (C2): a field PATCH with the current pdf_version → 200 (no false lock)."""
        tmpl = await _create_template(client, auth_headers, name="FreshLock")
        up = await _upload_pdf(client, auth_headers, tmpl["id"])
        current_version = up.json()["pdf_version"]
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={
                "field_definitions": [_field()],
                "pdf_version": current_version,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["field_definitions"]) == 1

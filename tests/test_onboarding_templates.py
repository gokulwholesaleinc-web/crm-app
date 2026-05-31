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
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from src.onboarding import storage

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
        assert body["pdf_path"] is None
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
        """Upload → 200, pdf_path set, version stays 1 on first upload."""
        tmpl = await _create_template(client, auth_headers, name="Upload")
        resp = await _upload_pdf(client, auth_headers, tmpl["id"])
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["pdf_path"] is not None
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


# =============================================================================
# PATCH /templates/{id}
# =============================================================================


class TestPatchTemplate:
    @pytest.mark.asyncio
    async def test_patch_metadata(self, client, auth_headers):
        """PATCH metadata fields → 200 with new values."""
        tmpl = await _create_template(client, auth_headers, name="Old")
        resp = await client.patch(
            f"/api/onboarding/templates/{tmpl['id']}",
            json={"name": "New Name", "requires_esign": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "New Name"
        assert body["requires_esign"] is True

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

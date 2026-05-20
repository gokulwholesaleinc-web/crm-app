"""Visual signature placement: schema validation + service-layer
1-indexed→0-indexed coord translation + end-to-end pixel stamp offset.

No mocks — the e2e class builds a real master PDF + real PNG, runs
``stamp_master_with_signature``, and parses the rendered content stream
back out to assert the stamp landed at the requested origin.
"""

from __future__ import annotations

import io
import os
import re
import secrets
import struct
import sys
import zlib
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../"))

from src.account.models import UserNotificationPrefs, UserPreferences  # noqa: F401
from src.activities.models import Activity  # noqa: F401
from src.assignment.models import AssignmentRule  # noqa: F401
from src.attachments.models import Attachment  # noqa: F401
from src.audit.models import AuditLog  # noqa: F401
from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.campaigns.models import (  # noqa: F401
    Campaign,
    CampaignMember,
    EmailCampaignStep,
    EmailTemplate,
)
from src.comments.models import Comment  # noqa: F401
from src.companies.models import Company  # noqa: F401
from src.contacts.models import Contact  # noqa: F401
from src.contracts.models import Contract  # noqa: F401
from src.core.models import EntityShare, EntityTag, Note, Tag  # noqa: F401
from src.dashboard.models import (  # noqa: F401
    DashboardChart,
    DashboardNumberCard,
    DashboardReportWidget,
)
from src.database import Base, get_db
from src.email.models import EmailQueue, EmailSettings, InboundEmail  # noqa: F401
from src.expenses.models import Expense  # noqa: F401
from src.filters.models import SavedFilter  # noqa: F401
from src.integrations.gmail.models import GmailConnection, GmailSyncState  # noqa: F401
from src.integrations.google_calendar.models import (  # noqa: F401
    CalendarSyncEvent,
    GoogleCalendarCredential,
)
from src.integrations.mailchimp.models import MailchimpConnection  # noqa: F401
from src.leads.models import Lead, LeadSource  # noqa: F401
from src.meta.models import CompanyMetaData, MetaCredential, MetaLeadCapture  # noqa: F401
from src.notifications.models import Notification  # noqa: F401
from src.opportunities.models import Opportunity, PipelineStage  # noqa: F401
from src.payments.models import Payment, Price, Product, StripeCustomer, Subscription  # noqa: F401
from src.proposals.models import Proposal
from src.proposals.pdf_stamper import StampInputs, _resolve_target_box, stamp_master_with_signature
from src.proposals.service import _coords_for_stamper
from src.quotes.models import (  # noqa: F401
    ProductBundle,
    ProductBundleItem,
    Quote,
    QuoteLineItem,
    QuoteTemplate,
)
from src.reports.models import SavedReport  # noqa: F401
from src.roles.models import DEFAULT_PERMISSIONS, Role, RoleName, UserRole  # noqa: F401
from src.sequences.models import Sequence, SequenceEnrollment  # noqa: F401
from src.webhooks.models import Webhook, WebhookDelivery  # noqa: F401
from src.whitelabel.models import Tenant, TenantSettings, TenantUser  # noqa: F401
from src.workflows.models import WorkflowExecution, WorkflowRule  # noqa: F401

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(autouse=True)
def _clear_user_cache():
    from src.auth.dependencies import _user_cache

    _user_cache.clear()
    yield
    _user_cache.clear()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, test_engine) -> AsyncGenerator[AsyncClient, None]:
    from src.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _make_user(
    db_session: AsyncSession,
    *,
    is_superuser: bool = True,
    role: str = "admin",
) -> User:
    user = User(
        email=f"user-{secrets.token_hex(4)}@test.com",
        hashed_password=get_password_hash("password"),
        full_name="Test User",
        is_active=True,
        is_approved=True,
        is_superuser=is_superuser,
        role=role,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


async def _make_draft_proposal(db: AsyncSession, owner: User) -> Proposal:
    """Draft proposals are editable; service.update() rejects signed rows."""
    proposal = Proposal(
        proposal_number=f"PR-{secrets.token_hex(4).upper()}",
        title="Coords Test",
        status="draft",
        amount=500.0,
        currency="USD",
        payment_type="one_time",
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)
    return proposal


def _make_valid_png() -> bytes:
    """A real 1x1 white-RGB PNG. The hex-string PNG that ships in
    ``test_pdf_stamper.py`` fails to decode under current Pillow, so
    the e2e class builds its own.
    """
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_chunk = (
        struct.pack(">I", len(ihdr_data))
        + b"IHDR"
        + ihdr_data
        + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data))
    )
    raw = b"\x00\xff\xff\xff"  # filter byte + 1 RGB pixel
    idat_data = zlib.compress(raw)
    idat_chunk = (
        struct.pack(">I", len(idat_data))
        + b"IDAT"
        + idat_data
        + struct.pack(">I", zlib.crc32(b"IDAT" + idat_data))
    )
    iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    return sig + ihdr_chunk + idat_chunk + iend_chunk


def _make_master_pdf(page_count: int = 2) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(page_count):
        c.setFont("Helvetica", 12)
        c.drawString(72, 720, f"Master page {i + 1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def _page_content_bytes(page) -> bytes:
    contents = page.get_contents()
    if contents is None:
        return b""
    if hasattr(contents, "get_data"):
        return contents.get_data()
    # pypdf returns an ArrayObject for chained streams.
    return b"".join(c.get_data() for c in contents)


_CM_RE = re.compile(rb"([\d.]+)\s+0\s+0\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+cm")


class TestSignatureFieldCoordsRoundtrip:
    async def test_patch_persists_valid_coords(self, client: AsyncClient, db_session: AsyncSession):
        user = await _make_user(db_session)
        proposal = await _make_draft_proposal(db_session, user)
        coords = {"page": 1, "x": 100.5, "y": 200.0, "w": 216.0, "h": 72.0}

        resp = await client.patch(
            f"/api/proposals/{proposal.id}",
            json={"signature_field_coords": coords},
            headers=_auth_headers(user),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["signature_field_coords"] == coords

        get_resp = await client.get(
            f"/api/proposals/{proposal.id}",
            headers=_auth_headers(user),
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["signature_field_coords"] == coords

        await db_session.refresh(proposal)
        assert proposal.signature_field_coords == coords

    async def test_patch_persists_multiple_coords(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await _make_user(db_session)
        proposal = await _make_draft_proposal(db_session, user)
        signature_coords = [
            {"page": 1, "x": 100.5, "y": 200.0, "w": 216.0, "h": 72.0},
            {"page": 1, "x": 120.0, "y": 80.0, "w": 160.0, "h": 48.0},
        ]
        date_coords = [
            {"page": 1, "x": 340.0, "y": 200.0, "w": 90.0, "h": 24.0},
            {"page": 1, "x": 340.0, "y": 80.0, "w": 90.0, "h": 24.0},
        ]

        resp = await client.patch(
            f"/api/proposals/{proposal.id}",
            json={
                "signature_field_coords": signature_coords,
                "date_field_coords": date_coords,
            },
            headers=_auth_headers(user),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["signature_field_coords"] == signature_coords
        assert body["date_field_coords"] == date_coords

        await db_session.refresh(proposal)
        assert proposal.signature_field_coords == signature_coords
        assert proposal.date_field_coords == date_coords

        trimmed_resp = await client.patch(
            f"/api/proposals/{proposal.id}",
            json={"signature_field_coords": signature_coords[:1]},
            headers=_auth_headers(user),
        )
        assert trimmed_resp.status_code == 200, trimmed_resp.text
        assert trimmed_resp.json()["signature_field_coords"] == signature_coords[:1]

    async def test_patch_null_coords_clears_back_to_auto_box(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await _make_user(db_session)
        proposal = await _make_draft_proposal(db_session, user)
        coords = {"page": 2, "x": 50.0, "y": 100.0, "w": 180.0, "h": 60.0}

        set_resp = await client.patch(
            f"/api/proposals/{proposal.id}",
            json={"signature_field_coords": coords},
            headers=_auth_headers(user),
        )
        assert set_resp.status_code == 200
        assert set_resp.json()["signature_field_coords"] == coords

        clear_resp = await client.patch(
            f"/api/proposals/{proposal.id}",
            json={"signature_field_coords": None},
            headers=_auth_headers(user),
        )
        assert clear_resp.status_code == 200
        assert clear_resp.json()["signature_field_coords"] is None

        get_resp = await client.get(
            f"/api/proposals/{proposal.id}",
            headers=_auth_headers(user),
        )
        assert get_resp.json()["signature_field_coords"] is None

    async def test_patch_without_coords_leaves_existing_alone(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await _make_user(db_session)
        proposal = await _make_draft_proposal(db_session, user)
        coords = {"page": 1, "x": 10.0, "y": 20.0, "w": 200.0, "h": 50.0}

        set_resp = await client.patch(
            f"/api/proposals/{proposal.id}",
            json={"signature_field_coords": coords},
            headers=_auth_headers(user),
        )
        assert set_resp.status_code == 200

        rename_resp = await client.patch(
            f"/api/proposals/{proposal.id}",
            json={"title": "Renamed"},
            headers=_auth_headers(user),
        )
        assert rename_resp.status_code == 200
        body = rename_resp.json()
        assert body["title"] == "Renamed"
        assert body["signature_field_coords"] == coords


class TestSignatureFieldCoordsValidation:
    """Pydantic should 422 garbage coords before any service-layer
    code runs — the stamper's clamp + auto-box guard remains as a
    second line of defense for fractional edge cases that slip past
    validation (e.g. a box drawn slightly past the page edge)."""

    @pytest.mark.parametrize(
        "bad_coords",
        [
            pytest.param({"page": 0, "x": 10, "y": 10, "w": 100, "h": 50}, id="page_zero"),
            pytest.param({"page": -1, "x": 10, "y": 10, "w": 100, "h": 50}, id="page_negative"),
            pytest.param({"page": 1, "x": -1, "y": 10, "w": 100, "h": 50}, id="x_negative"),
            pytest.param({"page": 1, "x": 10, "y": -5, "w": 100, "h": 50}, id="y_negative"),
            pytest.param({"page": 1, "x": 10, "y": 10, "w": 0, "h": 50}, id="w_zero"),
            pytest.param({"page": 1, "x": 10, "y": 10, "w": 100, "h": 0}, id="h_zero"),
            pytest.param({"page": 1, "x": 10, "y": 10, "w": 100}, id="missing_h"),
            pytest.param({"page": "two", "x": 10, "y": 10, "w": 100, "h": 50}, id="page_string"),
        ],
    )
    async def test_patch_rejects_invalid_coords(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        bad_coords: dict,
    ):
        user = await _make_user(db_session)
        proposal = await _make_draft_proposal(db_session, user)

        resp = await client.patch(
            f"/api/proposals/{proposal.id}",
            json={"signature_field_coords": bad_coords},
            headers=_auth_headers(user),
        )
        assert resp.status_code == 422, resp.text

    async def test_patch_rejects_invalid_coords_inside_array(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        user = await _make_user(db_session)
        proposal = await _make_draft_proposal(db_session, user)

        resp = await client.patch(
            f"/api/proposals/{proposal.id}",
            json={
                "signature_field_coords": [
                    {"page": 1, "x": 10, "y": 10, "w": 100, "h": 50},
                    {"page": 1, "x": 10, "y": 10, "w": 0, "h": 50},
                ],
            },
            headers=_auth_headers(user),
        )
        assert resp.status_code == 422, resp.text

    async def test_patch_rejects_empty_coords_array(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        user = await _make_user(db_session)
        proposal = await _make_draft_proposal(db_session, user)

        resp = await client.patch(
            f"/api/proposals/{proposal.id}",
            json={"signature_field_coords": []},
            headers=_auth_headers(user),
        )
        assert resp.status_code == 422, resp.text

    async def test_patch_rejects_too_many_coords(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        user = await _make_user(db_session)
        proposal = await _make_draft_proposal(db_session, user)

        resp = await client.patch(
            f"/api/proposals/{proposal.id}",
            json={
                "signature_field_coords": [
                    {"page": 1, "x": float(i), "y": 10, "w": 100, "h": 50} for i in range(101)
                ],
            },
            headers=_auth_headers(user),
        )
        assert resp.status_code == 422, resp.text


class TestSignatureFieldCoordsRejectsInfNaN:
    """``Field(gt=0)`` short-circuits ``inf > 0`` to ``True`` and NaN
    comparisons to ``False``; only the explicit ``allow_inf_nan=False``
    guard keeps these from landing in the DB as garbage. Exercised at
    the Pydantic layer directly so the test doesn't depend on whether
    the JSON serializer happens to emit non-conforming literals."""

    @pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
    def test_rejects_non_finite_w(self, bad: float):
        from pydantic import ValidationError

        from src.proposals.schemas import SignatureFieldCoords

        with pytest.raises(ValidationError):
            SignatureFieldCoords(page=1, x=10.0, y=10.0, w=bad, h=50.0)

    @pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
    def test_rejects_non_finite_xy(self, bad: float):
        from pydantic import ValidationError

        from src.proposals.schemas import SignatureFieldCoords

        with pytest.raises(ValidationError):
            SignatureFieldCoords(page=1, x=bad, y=10.0, w=100.0, h=50.0)


class TestStampUsesConfiguredBox:
    """End-to-end: picker-style coords flow through the service-layer
    converter into the real stamper and land at the requested origin
    on the rendered PDF. No mocks.

    The four tests in this class are sync (pure-function); the module
    has ``pytestmark = pytest.mark.asyncio`` for the route tests above,
    which makes pytest-asyncio emit a cosmetic warning here. The tests
    still run normally — the marker is a hint to the plugin, not a
    requirement that the function actually be async.
    """

    def _stamp_inputs(
        self,
        coords: dict | None,
        *,
        master_pages: int = 2,
    ) -> StampInputs:
        return StampInputs(
            master_pdf=_make_master_pdf(master_pages),
            signature_png=_make_valid_png(),
            coords=coords,
            signer_name="Test Signer",
            signer_email="test@example.com",
            signer_ip="203.0.113.7",
            signer_user_agent="StamperTest/1.0",
            signed_at=datetime(2026, 5, 14, 17, 30, tzinfo=UTC),
            proposal_number="PR-2026-COORDS-1",
        )

    def test_coords_for_stamper_translates_picker_payload(self):
        """1-indexed page → 0-indexed; w/h → width/height; floats preserved."""
        picker = {"page": 2, "x": 100.0, "y": 250.0, "w": 200.0, "h": 60.0}
        translated = _coords_for_stamper(picker)
        assert translated == {
            "page": 1,
            "x": 100.0,
            "y": 250.0,
            "width": 200.0,
            "height": 60.0,
        }

    def test_resolve_target_box_uses_converted_coords(self):
        master = _make_master_pdf(page_count=2)
        reader = PdfReader(io.BytesIO(master))
        translated = _coords_for_stamper({"page": 2, "x": 100.0, "y": 250.0, "w": 200.0, "h": 60.0})
        target_page_idx, box = _resolve_target_box(reader, translated)
        assert target_page_idx == 1
        assert box == (100.0, 250.0, 200.0, 60.0)

    def test_rendered_pdf_lands_image_origin_at_requested_xy(self):
        """The 1-px PNG gets ``preserveAspectRatio=True`` shrunk into a
        square inside the requested box and anchored to the SW corner.
        The cm matrix's tx/ty (image origin) must match the requested
        (x, y) within sub-pixel tolerance; the rendered w/h will be
        ≤ requested w/h (because aspect ratio is preserved on a 1×1
        image stretched into a 200×60 box → 60×60 square).
        """
        coords = {"page": 2, "x": 100.0, "y": 250.0, "w": 200.0, "h": 60.0}
        translated = _coords_for_stamper(coords)
        out = stamp_master_with_signature(self._stamp_inputs(translated))

        reader = PdfReader(io.BytesIO(out))
        # 2 master + 1 audit page; stamp lands on master page index 1.
        assert len(reader.pages) == 3
        target_bytes = _page_content_bytes(reader.pages[1])

        # Find the image-placement cm matrix. Reportlab emits a leading
        # ``1 0 0 1 0 0 cm`` (identity) for the canvas baseline plus the
        # actual image transform. We want the one whose w/h match the
        # rendered image size, not the identity row.
        matches = _CM_RE.findall(target_bytes)
        assert matches, f"no cm matrix found in target page content: {target_bytes!r}"

        # Pick the cm whose origin lands at the requested (x, y).
        placement = None
        for w_b, h_b, tx_b, ty_b in matches:
            w, h, tx, ty = (
                float(w_b),
                float(h_b),
                float(tx_b),
                float(ty_b),
            )
            if abs(tx - 100.0) < 1.0 and abs(ty - 250.0) < 1.0:
                placement = (w, h, tx, ty)
                break
        assert placement is not None, f"no cm matrix at requested origin in {matches!r}"
        w, h, tx, ty = placement
        # Origin must be exact (sub-pixel).
        assert abs(tx - 100.0) < 1.0
        assert abs(ty - 250.0) < 1.0
        # Rendered size is bounded by the requested box (preserveAspectRatio).
        assert 0 < w <= 200.0 + 1e-3
        assert 0 < h <= 60.0 + 1e-3

    def test_null_coords_falls_back_to_auto_box(self):
        """``_coords_for_stamper(None) → None`` and the stamper still
        renders (auto-box on the last page)."""
        assert _coords_for_stamper(None) is None

        out = stamp_master_with_signature(self._stamp_inputs(None))
        reader = PdfReader(io.BytesIO(out))
        assert len(reader.pages) == 3
        # Auto-box lands on the LAST master page (index 1 of 2-page master).
        last_master_bytes = _page_content_bytes(reader.pages[1])
        assert _CM_RE.search(
            last_master_bytes
        ), "auto-box still needs a cm operator on the last master page"

    def test_garbage_dict_returns_none(self):
        """Missing required keys → ``None`` so the stamper falls through
        to auto-box (matches the pre-validator defensive contract)."""
        assert _coords_for_stamper({"foo": "bar"}) is None
        # Empty dict is falsy → also None.
        assert _coords_for_stamper({}) is None

    def test_array_coords_are_strict(self):
        valid = {"page": 1, "x": 100.0, "y": 250.0, "w": 200.0, "h": 60.0}
        assert _coords_for_stamper([valid]) == [
            {
                "page": 0,
                "x": 100.0,
                "y": 250.0,
                "width": 200.0,
                "height": 60.0,
            }
        ]
        with pytest.raises(ValueError, match="At least one"):
            _coords_for_stamper([])
        with pytest.raises(ValueError, match="index 1"):
            _coords_for_stamper([valid, {"page": 1, "x": "nope"}])

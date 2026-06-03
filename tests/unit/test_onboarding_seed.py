"""No-mock unit tests for the onboarding template seed (P4).

The seed rebuilds Lorenzo's 6 Google Forms as 8 ``OnboardingTemplate`` rows
(the 2 upload-gated forms split into a questionnaire doc + an upload_request
doc). These tests are no-mock: ``seed_onboarding_templates`` runs against a REAL
``db_session`` (SQLite, from conftest) and every seeded ``field_definitions`` is
validated through the SAME kind handler the live save-path uses.

Coverage:
  * the seed creates all 8 templates with the expected names + kinds;
  * it is idempotent — a second run still yields 8 rows (UPSERT by name), and
    an out-of-band edit to ``field_definitions`` is healed back in place;
  * EVERY seeded definition passes its handler's ``validate_definitions`` (proves
    the seed is wire-valid by the live save-path's own rules);
  * the F4 password fields + the gov-ID upload carry ``sensitive=true``;
  * no field declares a ``prefill`` outside ``ALLOWED_PREFILL`` (no email
    prefill anywhere);
  * field ids match ``^[a-z0-9_]+$`` and are unique within each template;
  * service_tag choices match the §C.1 decision (universal=None; website /
    podcast / link-live tagged) and every non-null tag is a valid slug.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from src.onboarding.kinds import get_handler
from src.onboarding.models import OnboardingTemplate
from src.onboarding.prefill import ALLOWED_PREFILL
from src.onboarding.schemas import _SERVICE_TAG_RE
from src.onboarding.seed import (
    onboarding_template_specs,
    seed_onboarding_templates,
)

pytestmark = pytest.mark.asyncio

_ID_RE = re.compile(r"^[a-z0-9_]+$")

EXPECTED = {
    "Client Onboarding: Administrative Information": "questionnaire",
    "Client Onboarding: Identity Verification": "upload_request",
    "Client Strategy Insights": "questionnaire",
    "Client Onboarding: Branding Details": "questionnaire",
    "Client Onboarding: Brand Assets": "upload_request",
    "Website Onboarding Form": "questionnaire",
    "Link Label Studios — Podcast/Studio Intake": "questionnaire",
    "Link Live — Guest Intake": "questionnaire",
}


async def _count(db) -> int:
    rows = (await db.execute(select(OnboardingTemplate))).scalars().all()
    return len(rows)


# --- creation --------------------------------------------------------------


async def test_seed_creates_eight_templates(db_session):
    """A first seed materialises exactly the 8 expected name/kind templates."""
    templates = await seed_onboarding_templates(db_session)

    assert len(templates) == 8
    assert await _count(db_session) == 8
    by_name = {t.name: t for t in templates}
    assert set(by_name) == set(EXPECTED)
    for name, kind in EXPECTED.items():
        assert by_name[name].kind == kind
        assert by_name[name].is_active is True
        assert by_name[name].requires_esign is False


# --- idempotency -----------------------------------------------------------


async def test_seed_is_idempotent(db_session):
    """Running the seed twice creates no duplicates (UPSERT keyed on name)."""
    first = await seed_onboarding_templates(db_session)
    first_ids = sorted(t.id for t in first)

    second = await seed_onboarding_templates(db_session)
    second_ids = sorted(t.id for t in second)

    assert await _count(db_session) == 8
    # Same rows reused (same primary keys), not fresh inserts.
    assert first_ids == second_ids


async def test_seed_adopts_preexisting_same_name_row_no_duplicate(db_session):
    """S1: an admin-planted row sharing a seed name is ADOPTED, never duplicated.

    With ``uq_onboarding_templates_name`` enforced (create_all on the SQLite test
    DB) the seed's name-keyed UPSERT can't double-insert. Planting a same-name
    row first and then seeding leaves EXACTLY ONE row under that name (the
    planted row, refreshed in place to the seed spec) — no clobber-into-duplicate.
    """
    planted = OnboardingTemplate(
        name="Client Strategy Insights",  # collides with a seed template
        description="Admin's own version",
        service_tag="custom",
        kind="questionnaire",
        field_definitions=[
            {"id": "planted", "kind": "short_text", "label": "Planted",
             "required": False, "order": 1}
        ],
        requires_esign=False,
        is_active=True,
    )
    db_session.add(planted)
    await db_session.flush()
    planted_id = planted.id

    await seed_onboarding_templates(db_session)

    rows = (
        await db_session.execute(
            select(OnboardingTemplate).where(
                OnboardingTemplate.name == "Client Strategy Insights"
            )
        )
    ).scalars().all()
    # Exactly one row under that name (the planted one, adopted) — no duplicate.
    assert len(rows) == 1
    assert rows[0].id == planted_id
    # Total stays at the canonical 8 (adoption, not a 9th insert).
    assert await _count(db_session) == 8


async def test_seed_heals_edited_field_definitions(db_session):
    """A re-seed refreshes field_definitions in place after an out-of-band edit."""
    [tmpl] = [
        t
        for t in await seed_onboarding_templates(db_session)
        if t.name == "Client Strategy Insights"
    ]
    original = tmpl.field_definitions
    # Simulate drift: clobber the stored definition.
    tmpl.field_definitions = [{"id": "stale", "kind": "short_text",
                               "label": "Stale", "required": False, "order": 1}]
    await db_session.flush()

    await seed_onboarding_templates(db_session)
    await db_session.refresh(tmpl)

    assert await _count(db_session) == 8
    assert tmpl.field_definitions == original


# --- wire-validity: every definition passes its handler --------------------


async def test_every_definition_passes_its_handler(db_session):
    """Each seeded template's field_definitions passes validate_definitions."""
    for tmpl in await seed_onboarding_templates(db_session):
        handler = get_handler(tmpl.kind)
        # pdf_bytes=None — neither questionnaire nor upload_request reads a PDF.
        handler.validate_definitions(tmpl.field_definitions, pdf_bytes=None)


def test_specs_pass_handlers_without_db():
    """The pure specs validate too (no DB needed — the inventory is wire-valid)."""
    for spec in onboarding_template_specs():
        handler = get_handler(spec["kind"])
        handler.validate_definitions(spec["field_definitions"], pdf_bytes=None)


# --- sensitive fields ------------------------------------------------------


def test_form4_passwords_and_gov_id_are_sensitive():
    """The F4 hosting/platform passwords + the gov-ID upload carry sensitive=true."""
    specs = {s["name"]: s for s in onboarding_template_specs()}

    website = {f["id"]: f for f in specs["Website Onboarding Form"]["field_definitions"]}
    assert website["hosting_password"].get("sensitive") is True
    assert website["platform_password"].get("sensitive") is True
    # The two passwords are the ONLY sensitive fields on Form 4.
    sensitive_ids = {
        fid for fid, f in website.items() if f.get("sensitive")
    }
    assert sensitive_ids == {"hosting_password", "platform_password"}

    identity = specs["Client Onboarding: Identity Verification"]["field_definitions"]
    gov_id = {f["id"]: f for f in identity}["government_id"]
    assert gov_id.get("sensitive") is True


# --- prefill PII rule ------------------------------------------------------


def test_no_field_prefills_outside_allow_list():
    """No seeded field declares a prefill outside ALLOWED_PREFILL (no email)."""
    for spec in onboarding_template_specs():
        for field in spec["field_definitions"]:
            prefill = field.get("prefill")
            if prefill is not None:
                assert prefill in ALLOWED_PREFILL, (
                    f"{spec['name']}.{field['id']} prefill={prefill!r}"
                )
            # Defence in depth: an email-kind field must NEVER be prefilled.
            if field.get("kind") == "email":
                assert "prefill" not in field


def test_name_and_company_fields_are_prefilled():
    """The seed actually USES prefill where the brief calls for it."""
    specs = {s["name"]: s for s in onboarding_template_specs()}
    website = {f["id"]: f for f in specs["Website Onboarding Form"]["field_definitions"]}
    assert website["name"].get("prefill") == "contact.name"
    assert website["company"].get("prefill") == "company.name"

    strategy = {
        f["id"]: f for f in specs["Client Strategy Insights"]["field_definitions"]
    }
    assert strategy["client_name"].get("prefill") == "contact.name"


# --- id shape + uniqueness -------------------------------------------------


def test_field_ids_match_pattern_and_are_unique():
    """Every field id matches ^[a-z0-9_]+$ and is unique within its template."""
    for spec in onboarding_template_specs():
        seen: set[str] = set()
        for field in spec["field_definitions"]:
            fid = field["id"]
            assert _ID_RE.match(fid), f"{spec['name']}: bad id {fid!r}"
            assert fid not in seen, f"{spec['name']}: duplicate id {fid!r}"
            seen.add(fid)


def test_option_values_match_pattern_and_are_unique():
    """Every choice option value matches ^[a-z0-9_]+$ and is unique per field."""
    for spec in onboarding_template_specs():
        for field in spec["field_definitions"]:
            options = field.get("options")
            if not options:
                continue
            values = [o["value"] for o in options]
            assert len(set(values)) == len(values), (
                f"{spec['name']}.{field['id']} has duplicate option values"
            )
            for value in values:
                assert _ID_RE.match(value), (
                    f"{spec['name']}.{field['id']} bad option value {value!r}"
                )


# --- service_tag decision --------------------------------------------------


def test_service_tags_match_decision_and_are_valid_slugs():
    """Universal forms are null-tagged; service forms carry a valid slug tag."""
    tags = {s["name"]: s["service_tag"] for s in onboarding_template_specs()}

    assert tags["Website Onboarding Form"] == "website"
    assert tags["Link Label Studios — Podcast/Studio Intake"] == "podcast"
    assert tags["Link Live — Guest Intake"] == "link-live"
    # The 5 universal onboarding templates carry no tag.
    for name in (
        "Client Onboarding: Administrative Information",
        "Client Onboarding: Identity Verification",
        "Client Strategy Insights",
        "Client Onboarding: Branding Details",
        "Client Onboarding: Brand Assets",
    ):
        assert tags[name] is None

    # Every non-null tag must pass the API's own slug validator.
    for tag in tags.values():
        if tag is not None:
            assert _SERVICE_TAG_RE.match(tag), f"bad service_tag slug {tag!r}"

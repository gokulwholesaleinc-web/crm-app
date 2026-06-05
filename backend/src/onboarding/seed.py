"""Idempotent seed for the built-in onboarding starter templates (P4).

The starter definitions (Lorenzo's 6 Google Forms rebuilt as templates, with the
two upload-gated forms split into a questionnaire + an upload_request doc) live
in ``starter_definitions.py`` — ONE source, shared with the
``GET /templates/starters`` endpoint and the from-starter wizard. This module
only UPSERTs them into the DB.

Identity is the template ``name`` (a deterministic, human-readable string): the
seed UPSERTs by name so running it twice creates no duplicates and refreshes
``field_definitions`` / ``description`` / ``service_tag`` / ``kind`` in place.
The seeded ``field_definitions`` are wire-valid by construction — every kind's
``validate_definitions`` accepts them (the matrix test in
``tests/unit/test_onboarding_seed.py`` proves it).

This is a callable SEED MODULE, not a service and not a startup hook: nothing
here auto-runs at import or boot. Invoke it deliberately via ``python -m
src.onboarding.seed`` (the ``__main__`` guard) or by calling
``seed_onboarding_templates(db)`` from a test / one-off script.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from src.onboarding.kinds import get_handler
from src.onboarding.models import OnboardingTemplate

# Re-exported for back-compat: tests and callers import this from ``seed``.
from src.onboarding.starter_definitions import onboarding_template_specs

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = ["onboarding_template_specs", "seed_onboarding_templates"]


async def seed_onboarding_templates(db: AsyncSession) -> list[OnboardingTemplate]:
    """UPSERT the 8 onboarding starter templates idempotently, keyed on ``name``.

    For each spec: load the existing template by its deterministic ``name``;
    if present, refresh ``description`` / ``service_tag`` / ``kind`` /
    ``field_definitions`` in place (so a re-seed picks up an edited inventory
    without ever creating a duplicate); otherwise insert a fresh row. Every
    template's ``field_definitions`` is validated against its kind handler
    BEFORE the write, so the seed can never persist a definition the live
    save-path would reject (fail-closed, never a silent bad row).

    ``requires_esign`` is ``False`` for all (none are e-sign forms);
    ``is_active`` is ``True`` so they are immediately selectable / sendable.
    Returns the upserted templates in the spec order. The caller owns the
    commit (mirrors the other seeds, and lets a test roll back).
    """
    specs = onboarding_template_specs()
    names = [spec["name"] for spec in specs]
    existing = {
        tmpl.name: tmpl
        for tmpl in (
            await db.execute(
                select(OnboardingTemplate).where(
                    OnboardingTemplate.name.in_(names)
                )
            )
        ).scalars().all()
    }

    result: list[OnboardingTemplate] = []
    for spec in specs:
        # Validate against the SAME handler the live save-path uses, so a
        # seeded definition can never drift from what the API would accept.
        handler = get_handler(spec["kind"])
        handler.validate_definitions(spec["field_definitions"], pdf_bytes=None)

        template = existing.get(spec["name"])
        if template is None:
            template = OnboardingTemplate(
                name=spec["name"],
                description=spec["description"],
                service_tag=spec["service_tag"],
                kind=spec["kind"],
                field_definitions=spec["field_definitions"],
                requires_esign=False,
                is_active=True,
            )
            db.add(template)
            logger.info("onboarding seed: creating template %r", spec["name"])
        else:
            template.description = spec["description"]
            template.service_tag = spec["service_tag"]
            template.kind = spec["kind"]
            template.field_definitions = spec["field_definitions"]
            template.requires_esign = False
            template.is_active = True
            logger.info("onboarding seed: updating template %r", spec["name"])
        result.append(template)

    await db.flush()
    return result


async def _run() -> None:
    """Open a real session, seed, and commit (the ``python -m`` entry point)."""
    from src.database import async_session_maker

    async with async_session_maker() as db:
        templates = await seed_onboarding_templates(db)
        await db.commit()
        logger.info("onboarding seed: upserted %d templates", len(templates))


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())

"""Endpoints for the current user's personal data — /api/me/*."""

import logging
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from src.auth.models import User
from src.core.models import EntityShare
from src.core.router_utils import CurrentUser, DBSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/me", tags=["me"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class SharedWithMeItem(BaseModel):
    entity_type: str
    entity_id: int
    title: str
    owner_name: str | None
    shared_at: datetime
    permission_level: str


class SharedWithMeResponse(BaseModel):
    items_by_type: dict[str, list[SharedWithMeItem]]
    total: int


# ---------------------------------------------------------------------------
# Dispatch table: entity_type -> (Model, title_attr, owner_id_attr)
# title_attr may be a callable that takes a row and returns a string.
# ---------------------------------------------------------------------------

def _build_dispatch() -> dict:
    """Build the entity-type dispatch table lazily to avoid import cycles."""
    from src.campaigns.models import Campaign
    from src.companies.models import Company
    from src.contacts.models import Contact
    from src.leads.models import Lead
    from src.opportunities.models import Opportunity
    from src.proposals.models import Proposal

    # Quotes rollup retired 2026-05-14 — quotes router unmounted.
    # Contracts rollup retired 2026-05-14 — contracts router unmounted.
    return {
        "leads": (Lead, lambda r: r.full_name or r.company_name or f"Lead #{r.id}", "owner_id"),
        "opportunities": (Opportunity, lambda r: r.name, "owner_id"),
        "proposals": (Proposal, lambda r: r.title, "owner_id"),
        "campaigns": (Campaign, lambda r: r.name, "owner_id"),
        "contacts": (Contact, lambda r: r.full_name, "owner_id"),
        "companies": (Company, lambda r: r.name, "owner_id"),
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/shared", response_model=SharedWithMeResponse)
async def get_shared_with_me(
    current_user: CurrentUser,
    db: DBSession,
) -> SharedWithMeResponse:
    """Return records shared with the current user that they do not own.

    Groups results by entity_type, capped at 5 most-recent per type.
    Uses one query per entity_type (no N+1 within a type).
    """
    # 1. Fetch the most-recent EntityShare rows. Capped at 200 — a power
    # user with thousands of shared rows (e.g., post-backfill on a large
    # tenant) should not pay a full-table scan to populate a 5-per-type
    # widget. 200 is a safe ceiling for "5 per known type with headroom".
    shares_result = await db.execute(
        select(EntityShare)
        .where(EntityShare.shared_with_user_id == current_user.id)
        .order_by(EntityShare.created_at.desc())
        .limit(200)
    )
    all_shares: list[EntityShare] = list(shares_result.scalars().all())

    if not all_shares:
        return SharedWithMeResponse(items_by_type={}, total=0)

    # 2. Group shares by entity_type, keeping only the 5 most recent per type.
    grouped: dict[str, list[EntityShare]] = {}
    for share in all_shares:
        bucket = grouped.setdefault(share.entity_type, [])
        if len(bucket) < 5:
            bucket.append(share)

    dispatch = _build_dispatch()
    items_by_type: dict[str, list[SharedWithMeItem]] = {}

    for entity_type, shares in grouped.items():
        if entity_type not in dispatch:
            logger.warning(
                "shared-with-me: unknown entity_type %r for user_id=%s — skipping %d share(s)",
                entity_type,
                current_user.id,
                len(shares),
            )
            continue

        model, title_fn, owner_id_attr = dispatch[entity_type]
        entity_ids = [s.entity_id for s in shares]

        # 3. Bulk-fetch the underlying entity rows (single query per type).
        rows_result = await db.execute(
            select(model).where(model.id.in_(entity_ids))
        )
        rows_by_id = {r.id: r for r in rows_result.scalars().all()}

        # 4. Collect the owner_ids we need to resolve.
        owner_ids: set[int] = set()
        for row in rows_by_id.values():
            oid = getattr(row, owner_id_attr, None)
            if oid is not None:
                owner_ids.add(oid)

        # 5. Bulk-fetch User rows for owner names (single query).
        owner_name_by_id: dict[int, str] = {}
        if owner_ids:
            users_result = await db.execute(
                select(User.id, User.full_name).where(User.id.in_(owner_ids))
            )
            owner_name_by_id = {uid: name for uid, name in users_result.all()}

        # 6. Build response items preserving the newest-first order from shares.
        type_items: list[SharedWithMeItem] = []
        for share in shares:
            row = rows_by_id.get(share.entity_id)
            if row is None:
                # Entity was deleted — skip silently.
                continue
            oid = getattr(row, owner_id_attr, None)
            try:
                title = title_fn(row)
            except Exception:
                logger.warning(
                    "shared-with-me: title_fn raised for %s/%s — using id fallback",
                    entity_type,
                    share.entity_id,
                    exc_info=True,
                )
                title = f"{entity_type.rstrip('s').capitalize()} #{share.entity_id}"
            type_items.append(
                SharedWithMeItem(
                    entity_type=entity_type,
                    entity_id=share.entity_id,
                    title=title,
                    owner_name=owner_name_by_id.get(oid) if oid is not None else None,
                    shared_at=share.created_at,
                    permission_level=share.permission_level,
                )
            )

        if type_items:
            items_by_type[entity_type] = type_items

    total = sum(len(v) for v in items_by_type.values())
    return SharedWithMeResponse(items_by_type=items_by_type, total=total)

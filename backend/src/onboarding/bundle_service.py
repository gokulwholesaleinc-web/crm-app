"""Service layer for onboarding template bundles ("saved packets", §4.4/4.6).

A bundle is a named, ordered list of template references staff assemble once and
reuse. The wizard mints a fresh template per item (reusing
``OnboardingTemplateService._build_template`` so the batch inherits 100% of the
validation + owner-setting — audit B1) and records them as ordered members, all
in one transaction (nothing partial). Order-mutating ops take a ``FOR UPDATE``
lock on the bundle row before the shared two-pass rewrite (mirrors
``_lock_proposal``); per-member send-readiness is the shared
``template_send_status`` so the bundle detail, the packet loader, and the
selection asserter all agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.onboarding.models import (
    OnboardingTemplate,
    OnboardingTemplateBundle,
    OnboardingTemplateBundleItem,
)
from src.onboarding.ordering import reorder_by_display_order
from src.onboarding.packet_errors import (
    PacketNotFoundError,
    PacketValidationError,
)
from src.onboarding.service import (
    FieldDefinitionError,
    OnboardingTemplateService,
    count_signature_fields,
    template_send_status,
)
from src.onboarding.starter_definitions import get_starter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.auth.models import User
    from src.onboarding.bundle_schemas import BundleWizardItem

# Ceiling on documents per packet (§10 Q4: floor 1, ceiling ~20).
_MAX_BUNDLE_ITEMS = 20


@dataclass(frozen=True)
class BundleMemberView:
    """One resolved bundle member + its computed readiness (detail view)."""

    item_id: int
    template_id: int
    display_order: int
    name: str
    kind: str
    requires_esign: bool
    is_active: bool
    has_pdf: bool
    send_ready: bool
    send_reason: str | None


@dataclass(frozen=True)
class BundleSummaryView:
    """A saved packet in the list view (counts + whole-bundle readiness)."""

    id: int
    name: str
    description: str | None
    is_active: bool
    item_count: int
    send_ready: bool
    created_at: object
    updated_at: object


class BundleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ----------------------------------------------------------------------
    # Create (wizard) — §4.4 atomic, reuse-based.
    # ----------------------------------------------------------------------
    async def create_from_wizard(
        self,
        *,
        current_user: User,
        name: str,
        description: str | None,
        items: list[BundleWizardItem],
    ) -> OnboardingTemplateBundle:
        """Mint a template per item and record them as an ordered bundle.

        All-or-nothing: one bad item (invalid def / e-sign clone / duplicate
        name) leaves zero templates AND no bundle. Rejects an empty item list
        (§C3) and caps at ``_MAX_BUNDLE_ITEMS``.
        """
        if not items:
            raise PacketValidationError(
                "A saved packet must contain at least one document."
            )
        if len(items) > _MAX_BUNDLE_ITEMS:
            raise PacketValidationError(
                f"A saved packet can hold at most {_MAX_BUNDLE_ITEMS} documents."
            )

        resolved = [await self._resolve_item(item) for item in items]
        item_names = [nm for nm, _ in resolved]
        if len(set(item_names)) != len(item_names):
            raise PacketValidationError(
                "Two documents in this packet share a name; each needs a "
                "unique name."
            )
        # Friendly pre-checks; the unique constraints are the real race guard.
        await self._assert_template_names_free(item_names)
        await self._assert_bundle_name_free(name)

        # Build via _build_template (reuses validation + owner-setting, B1). A
        # bad field def or an e-sign clone surfaces as FieldDefinitionError.
        try:
            templates = [
                OnboardingTemplateService._build_template(
                    current_user=current_user, name=nm, **kwargs
                )
                for nm, kwargs in resolved
            ]
        except FieldDefinitionError as exc:
            raise PacketValidationError(str(exc)) from exc

        self.db.add_all(templates)
        try:
            # Single flush for the whole batch → ONE IntegrityError to catch.
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()  # whole-transaction rollback; nothing partial
            raise PacketValidationError(
                "One or more document names already exist."
            ) from exc

        bundle = OnboardingTemplateBundle(
            name=name,
            description=description,
            created_by_id=current_user.id,
            updated_by_id=current_user.id,
        )
        self.db.add(bundle)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise PacketValidationError(
                "A saved packet with this name already exists."
            ) from exc

        for order, template in enumerate(templates):
            self.db.add(
                OnboardingTemplateBundleItem(
                    bundle_id=bundle.id,
                    template_id=template.id,
                    display_order=order,
                    created_by_id=current_user.id,
                    updated_by_id=current_user.id,
                )
            )
        await self.db.flush()
        await self.db.refresh(bundle)
        return bundle

    async def _resolve_item(self, item: BundleWizardItem) -> tuple[str, dict]:
        """Resolve one wizard item to ``(name, _build_template kwargs)``.

        Raises ``PacketValidationError`` on a bad clone source / unknown starter
        (the batch is all-or-nothing, so a bad ref is a clean 422).
        """
        if item.source == "clone":
            source = await self._get_template(item.source_template_id)
            if source is None:
                raise PacketValidationError(
                    f"Source template {item.source_template_id} not found."
                )
            try:
                kwargs = OnboardingTemplateService.clone_build_kwargs(source)
            except FieldDefinitionError as exc:
                raise PacketValidationError(str(exc)) from exc
            return item.name, kwargs
        if item.source == "starter":
            spec = get_starter(item.starter_key or "")
            if spec is None:
                raise PacketValidationError(
                    f"Unknown starter '{item.starter_key}'."
                )
            return item.name, OnboardingTemplateService.starter_build_kwargs(spec)
        # blank — a fresh template from the item's own spec.
        return item.name, {
            "description": item.description,
            "service_tag": item.service_tag,
            "requires_esign": False,
            "kind": item.kind,
            "field_definitions": item.field_definitions,
        }

    # ----------------------------------------------------------------------
    # Read.
    # ----------------------------------------------------------------------
    async def list_bundles(
        self, *, include_inactive: bool = False
    ) -> list[BundleSummaryView]:
        """Global team library — no owner filter (§4.8)."""
        query = select(OnboardingTemplateBundle)
        if not include_inactive:
            query = query.where(OnboardingTemplateBundle.is_active.is_(True))
        query = query.order_by(OnboardingTemplateBundle.created_at.desc())
        bundles = list((await self.db.execute(query)).scalars().all())
        if not bundles:
            return []

        bundle_ids = [b.id for b in bundles]
        # One query for every member's readiness fields (no N+1).
        rows = (
            await self.db.execute(
                select(
                    OnboardingTemplateBundleItem.bundle_id,
                    OnboardingTemplate.is_active,
                    OnboardingTemplate.kind,
                    OnboardingTemplate.pdf_path,
                    OnboardingTemplate.field_definitions,
                )
                .join(
                    OnboardingTemplate,
                    OnboardingTemplate.id
                    == OnboardingTemplateBundleItem.template_id,
                )
                .where(OnboardingTemplateBundleItem.bundle_id.in_(bundle_ids))
            )
        ).all()
        counts = dict.fromkeys(bundle_ids, 0)
        ready = dict.fromkeys(bundle_ids, True)
        for bundle_id, is_active, kind, pdf_path, field_definitions in rows:
            counts[bundle_id] += 1
            member_ready, _ = template_send_status(
                is_active=is_active,
                kind=kind,
                pdf_path=pdf_path,
                field_count=len(field_definitions or []),
                signature_field_count=count_signature_fields(field_definitions),
            )
            if not member_ready:
                ready[bundle_id] = False

        return [
            BundleSummaryView(
                id=b.id,
                name=b.name,
                description=b.description,
                is_active=b.is_active,
                item_count=counts[b.id],
                # A retired packet, an empty one, or one with any not-ready
                # member can't be sent.
                send_ready=b.is_active and counts[b.id] > 0 and ready[b.id],
                created_at=b.created_at,
                updated_at=b.updated_at,
            )
            for b in bundles
        ]

    async def get_bundle_detail(
        self, bundle_id: int
    ) -> tuple[OnboardingTemplateBundle, list[BundleMemberView], bool]:
        """Return ``(bundle, ordered members, whole-bundle send_ready)``.

        Each member carries its backend-computed ``send_ready`` + reason
        (``template_send_status``) so the frontend reads a flag and never
        re-derives readiness (B5/D1). 404 if the bundle is missing.
        """
        bundle = await self._get_bundle(bundle_id)
        if bundle is None:
            raise PacketNotFoundError(f"Saved packet {bundle_id} not found.")
        rows = (
            await self.db.execute(
                select(OnboardingTemplateBundleItem, OnboardingTemplate)
                .join(
                    OnboardingTemplate,
                    OnboardingTemplate.id
                    == OnboardingTemplateBundleItem.template_id,
                )
                .where(OnboardingTemplateBundleItem.bundle_id == bundle_id)
                .order_by(
                    OnboardingTemplateBundleItem.display_order,
                    OnboardingTemplateBundleItem.id,
                )
            )
        ).all()
        members: list[BundleMemberView] = []
        all_ready = True
        for item, template in rows:
            member_ready, reason = template_send_status(
                is_active=template.is_active,
                kind=template.kind,
                pdf_path=template.pdf_path,
                field_count=len(template.field_definitions or []),
                signature_field_count=count_signature_fields(
                    template.field_definitions
                ),
            )
            if not member_ready:
                all_ready = False
            members.append(
                BundleMemberView(
                    item_id=item.id,
                    template_id=template.id,
                    display_order=item.display_order,
                    name=template.name,
                    kind=template.kind,
                    requires_esign=template.requires_esign,
                    is_active=template.is_active,
                    has_pdf=template.pdf_path is not None,
                    send_ready=member_ready,
                    send_reason=reason,
                )
            )
        # A retired bundle, an empty one, or one with any not-ready member can't
        # be sent (the bundle's own is_active gates it too — a packet retired
        # after the list was fetched must not read as ready).
        send_ready = bundle.is_active and len(members) > 0 and all_ready
        return bundle, members, send_ready

    # ----------------------------------------------------------------------
    # Mutations — rename/retire + order ops (the latter behind a FOR UPDATE lock).
    # ----------------------------------------------------------------------
    async def update_bundle(
        self, bundle_id: int, *, current_user: User, **fields
    ) -> OnboardingTemplateBundle:
        """Apply a partial update (``fields`` already exclude_unset): rename /
        re-describe / retire-restore. Name collision → 422."""
        bundle = await self._get_bundle(bundle_id)
        if bundle is None:
            raise PacketNotFoundError(f"Saved packet {bundle_id} not found.")
        for key, value in fields.items():
            setattr(bundle, key, value)
        bundle.updated_by_id = current_user.id
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise PacketValidationError(
                "A saved packet with this name already exists."
            ) from exc
        await self.db.refresh(bundle)
        return bundle

    async def reorder(
        self, bundle_id: int, *, ordered_item_ids: list[int], current_user: User
    ) -> tuple[OnboardingTemplateBundle, list[BundleMemberView], bool]:
        """Reassign member ``display_order`` from a permutation of item ids.

        Takes the bundle ``FOR UPDATE`` lock FIRST (V3-1) so two staff reordering
        at once can't race ``uq_..._order`` into a raw 500, then runs the shared
        two-pass rewrite. The lock is a no-op on the SQLite test harness
        (review-asserted, not test-proven — §3/B3).
        """
        await self._lock_bundle(bundle_id)
        items = await self._list_items(bundle_id)
        by_id = {it.id: it for it in items}
        if set(ordered_item_ids) != set(by_id) or len(ordered_item_ids) != len(
            by_id
        ):
            raise PacketValidationError(
                "ordered_item_ids must be exactly the current item ids."
            )
        for item in items:
            item.updated_by_id = current_user.id

        def _set_order(item: OnboardingTemplateBundleItem, order: int) -> None:
            item.display_order = order

        await reorder_by_display_order(
            items, ordered_item_ids, set_order=_set_order, flush=self.db.flush
        )
        return await self.get_bundle_detail(bundle_id)

    async def add_item(
        self, bundle_id: int, *, template_id: int, current_user: User
    ) -> tuple[OnboardingTemplateBundle, list[BundleMemberView], bool]:
        """Append an existing template to the bundle (behind the lock).

        Readiness is NOT gated here — a member may be added before it is
        send-ready (e.g. a blank e-sign awaiting a PDF); the detail surfaces that.
        Duplicate template → 422 (the unique constraint is the real guard).
        """
        await self._lock_bundle(bundle_id)
        template = await self._get_template(template_id)
        if template is None:
            raise PacketValidationError(f"Template {template_id} not found.")
        items = await self._list_items(bundle_id)
        if len(items) >= _MAX_BUNDLE_ITEMS:
            raise PacketValidationError(
                f"A saved packet can hold at most {_MAX_BUNDLE_ITEMS} documents."
            )
        if any(it.template_id == template_id for it in items):
            raise PacketValidationError("That template is already in this packet.")
        next_order = max((it.display_order for it in items), default=-1) + 1
        self.db.add(
            OnboardingTemplateBundleItem(
                bundle_id=bundle_id,
                template_id=template_id,
                display_order=next_order,
                created_by_id=current_user.id,
                updated_by_id=current_user.id,
            )
        )
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise PacketValidationError(
                "That template is already in this packet."
            ) from exc
        return await self.get_bundle_detail(bundle_id)

    async def remove_item(
        self, bundle_id: int, item_id: int, *, current_user: User
    ) -> None:
        """Remove one member (behind the lock). Refuses to remove the LAST one
        (§C3) — delete the whole packet instead."""
        await self._lock_bundle(bundle_id)
        items = await self._list_items(bundle_id)
        target = next((it for it in items if it.id == item_id), None)
        if target is None:
            raise PacketNotFoundError(
                f"Document {item_id} is not in this packet."
            )
        if len(items) <= 1:
            raise PacketValidationError(
                "A saved packet must keep at least one document; delete the "
                "packet instead."
            )
        await self.db.delete(target)
        await self.db.flush()

    async def delete_bundle(self, bundle_id: int) -> None:
        """Hard-delete a bundle; its items CASCADE (on real Postgres). The
        templates the bundle minted are NOT touched (no template_id cascade)."""
        bundle = await self._get_bundle(bundle_id)
        if bundle is None:
            raise PacketNotFoundError(f"Saved packet {bundle_id} not found.")
        await self.db.delete(bundle)
        await self.db.flush()

    # ----------------------------------------------------------------------
    # Internals.
    # ----------------------------------------------------------------------
    async def _get_bundle(
        self, bundle_id: int
    ) -> OnboardingTemplateBundle | None:
        return (
            await self.db.execute(
                select(OnboardingTemplateBundle).where(
                    OnboardingTemplateBundle.id == bundle_id
                )
            )
        ).scalar_one_or_none()

    async def _lock_bundle(self, bundle_id: int) -> OnboardingTemplateBundle:
        """``SELECT bundle ... FOR UPDATE`` so concurrent order mutations
        serialize (mirrors ``_lock_proposal``). ``with_for_update`` is a silent
        no-op on SQLite, so the test harness is unaffected (V3-1)."""
        bundle = (
            await self.db.execute(
                select(OnboardingTemplateBundle)
                .where(OnboardingTemplateBundle.id == bundle_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if bundle is None:
            raise PacketNotFoundError(f"Saved packet {bundle_id} not found.")
        return bundle

    async def _list_items(
        self, bundle_id: int
    ) -> list[OnboardingTemplateBundleItem]:
        return list(
            (
                await self.db.execute(
                    select(OnboardingTemplateBundleItem)
                    .where(OnboardingTemplateBundleItem.bundle_id == bundle_id)
                    .order_by(
                        OnboardingTemplateBundleItem.display_order,
                        OnboardingTemplateBundleItem.id,
                    )
                )
            )
            .scalars()
            .all()
        )

    async def _get_template(
        self, template_id: int | None
    ) -> OnboardingTemplate | None:
        if template_id is None:
            return None
        return (
            await self.db.execute(
                select(OnboardingTemplate).where(
                    OnboardingTemplate.id == template_id
                )
            )
        ).scalar_one_or_none()

    async def _assert_template_names_free(self, names: list[str]) -> None:
        existing = set(
            (
                await self.db.execute(
                    select(OnboardingTemplate.name).where(
                        OnboardingTemplate.name.in_(names)
                    )
                )
            )
            .scalars()
            .all()
        )
        if existing:
            joined = ", ".join(sorted(existing))
            raise PacketValidationError(
                f"These document names already exist: {joined}. Rename them and "
                "try again."
            )

    async def _assert_bundle_name_free(self, name: str) -> None:
        exists = (
            await self.db.execute(
                select(OnboardingTemplateBundle.id).where(
                    OnboardingTemplateBundle.name == name
                )
            )
        ).scalar_one_or_none()
        if exists is not None:
            raise PacketValidationError(
                "A saved packet with this name already exists."
            )

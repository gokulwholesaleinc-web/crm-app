"""Sharing endpoints for record collaboration between users."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import aliased

from src.audit.service import AuditService
from src.auth.models import User
from src.companies.models import Company
from src.contacts.models import Contact
from src.core.constants import HTTPStatus
from src.core.data_scope import (
    DataScope,
    check_record_access_or_shared,
    get_data_scope,
    invalidate_scope_cache,
)
from src.core.entity_access import _resolve_entity
from src.core.entity_types import canonical_plural, canonical_singular, entity_type_variants
from src.core.models import EntityShare
from src.core.router_utils import CurrentUser, DBSession
from src.core.share_permissions import (
    VALID_SHARE_PERMISSIONS,
    require_owner_or_manager_access,
)
from src.leads.models import Lead
from src.notifications.service import NotificationService
from src.proposals.models import Proposal

router = APIRouter(prefix="/api/sharing", tags=["sharing"])

ADMIN_BULK_ENTITY_TYPES = {"contacts", "companies", "leads", "proposals"}
ADMIN_BULK_MAX_RECORDS = 500


class ShareRequest(BaseModel):
    entity_type: str
    entity_id: int
    shared_with_user_id: int
    permission_level: str = "view"


class ShareResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    shared_with_user_id: int
    shared_by_user_id: int
    permission_level: str

    model_config = {"from_attributes": True}


class ShareListResponse(BaseModel):
    items: list[ShareResponse]


class AdminBulkShareRequest(BaseModel):
    entity_type: str
    entity_ids: list[int]
    shared_with_user_id: int
    permission_level: str = "view"


class AdminBulkShareResult(BaseModel):
    entity_id: int
    status: Literal["created", "updated", "skipped", "failed"]
    detail: str


class AdminBulkShareResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    failed: int
    items: list[AdminBulkShareResult]


@router.post("", response_model=ShareResponse, status_code=HTTPStatus.CREATED)
async def share_entity(
    request: ShareRequest,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Share an entity with another user.

    Caller must own the target record or have manager/admin scope. Prevents
    view-only recipients from granting peers access or escalating permissions.
    """
    if request.permission_level not in VALID_SHARE_PERMISSIONS:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="permission_level must be 'view', 'edit', or 'assignee'",
        )

    if request.shared_with_user_id == current_user.id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Cannot share a record with yourself",
        )

    entity, plural = await _resolve_entity(db, request.entity_type, request.entity_id)
    if entity is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"{request.entity_type} {request.entity_id} not found",
        )
    entity_type = plural
    require_owner_or_manager_access(
        entity,
        current_user,
        data_scope.role_name,
        detail="Only the owner, admins, and managers can share this record",
    )

    target_result = await db.execute(
        select(User.id).where(
            User.id == request.shared_with_user_id,
            User.is_active.is_(True),
        )
    )
    if target_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="User to share with not found",
        )

    entity_type_inputs = entity_type_variants(request.entity_type)
    existing = await db.execute(
        select(EntityShare.id)
        .where(
            EntityShare.entity_type.in_(entity_type_inputs),
            EntityShare.entity_id == request.entity_id,
            EntityShare.shared_with_user_id == request.shared_with_user_id,
        )
        .limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT,
            detail="This record is already shared with the specified user",
        )

    share = EntityShare(
        entity_type=entity_type,
        entity_id=request.entity_id,
        shared_with_user_id=request.shared_with_user_id,
        shared_by_user_id=current_user.id,
        permission_level=request.permission_level,
    )
    db.add(share)
    await db.flush()

    # Audit row keyed to the shared record so it surfaces in that entity's history.
    await AuditService(db).log_change(
        entity_type=canonical_singular(entity_type),
        entity_id=request.entity_id,
        user_id=current_user.id,
        action="share",
        changes=[{
            "field": "shared_with_user_id",
            "old": None,
            "new": request.shared_with_user_id,
            "permission_level": request.permission_level,
        }],
    )

    sharer_name = current_user.full_name or current_user.email
    entity_singular = canonical_singular(entity_type)
    if request.permission_level == "assignee":
        notif_type = "record_assigned_to_you"
        title = f"{sharer_name} assigned a {entity_singular} to you"
        message = f"You have been assigned a {entity_singular} (id={request.entity_id})"
    else:
        notif_type = "entity_shared_with_you"
        title = f"{sharer_name} shared a {entity_singular} with you"
        message = f"A {entity_singular} was shared with you (id={request.entity_id})"

    notif_service = NotificationService(db)
    await notif_service.create_notification(
        user_id=request.shared_with_user_id,
        type=notif_type,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=request.entity_id,
    )

    await db.commit()
    await db.refresh(share)
    invalidate_scope_cache(request.shared_with_user_id)

    return ShareResponse.model_validate(share)


@router.get("/{entity_type}/{entity_id}", response_model=ShareListResponse)
async def list_entity_shares(
    entity_type: str,
    entity_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """List all shares for a specific entity."""
    entity, plural = await _resolve_entity(db, entity_type, entity_id)
    if entity is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"{entity_type} {entity_id} not found",
        )

    check_record_access_or_shared(
        entity,
        current_user,
        data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(plural),
        entity_type=plural,
    )

    entity_type_inputs = entity_type_variants(entity_type)
    result = await db.execute(
        select(EntityShare).where(
            EntityShare.entity_type.in_(entity_type_inputs),
            EntityShare.entity_id == entity_id,
        )
    )
    shares = list(result.scalars().all())
    return ShareListResponse(
        items=[ShareResponse.model_validate(s) for s in shares]
    )


@router.delete("/{share_id}", status_code=HTTPStatus.NO_CONTENT)
async def revoke_share(
    share_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Revoke a share as the sharer, recipient, or admin."""
    result = await db.execute(
        select(EntityShare).where(EntityShare.id == share_id)
    )
    share = result.scalar_one_or_none()
    if not share:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Share not found",
        )

    if (
        not current_user.is_superuser
        and data_scope.role_name != "admin"
        and current_user.id not in (share.shared_by_user_id, share.shared_with_user_id)
    ):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="You do not have permission to revoke this share",
        )

    shared_with_id = share.shared_with_user_id
    revoked_entity_type = share.entity_type
    revoked_entity_id = share.entity_id
    revoked_permission = share.permission_level
    await db.delete(share)
    await db.flush()

    # Mirror audit row for the unshare event, same keying as POST /api/sharing.
    await AuditService(db).log_change(
        entity_type=canonical_singular(revoked_entity_type),
        entity_id=revoked_entity_id,
        user_id=current_user.id,
        action="unshare",
        changes=[{
            "field": "shared_with_user_id",
            "old": shared_with_id,
            "new": None,
            "permission_level": revoked_permission,
        }],
    )
    await db.commit()
    invalidate_scope_cache(shared_with_id)


@router.post("/admin/bulk", response_model=AdminBulkShareResponse)
async def admin_bulk_share(
    request: AdminBulkShareRequest,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Bulk grant or update record shares as an admin."""
    if not current_user.is_superuser and data_scope.role_name != "admin":
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Only admins can access this endpoint",
        )

    if request.permission_level not in VALID_SHARE_PERMISSIONS:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="permission_level must be 'view', 'edit', or 'assignee'",
        )

    if request.shared_with_user_id == current_user.id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Cannot share records with yourself",
        )

    requested_entity_type = request.entity_type.strip().lower()
    entity_type_inputs = entity_type_variants(requested_entity_type)
    entity_type = canonical_singular(requested_entity_type)
    entity_plural = canonical_plural(entity_type)
    if entity_plural not in ADMIN_BULK_ENTITY_TYPES:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="entity_type must be contacts, companies, leads, or proposals",
        )

    entity_ids = list(dict.fromkeys(request.entity_ids))
    if not entity_ids:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="entity_ids must include at least one record id",
        )
    if len(entity_ids) > ADMIN_BULK_MAX_RECORDS:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Bulk sharing is limited to {ADMIN_BULK_MAX_RECORDS} records",
        )

    target_result = await db.execute(
        select(User).where(
            User.id == request.shared_with_user_id,
            User.is_active.is_(True),
        )
    )
    target_user = target_result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="User to share with not found",
        )

    existing_result = await db.execute(
        select(EntityShare).where(
            EntityShare.entity_type.in_(entity_type_inputs),
            EntityShare.entity_id.in_(entity_ids),
            EntityShare.shared_with_user_id == request.shared_with_user_id,
        )
    )
    existing_by_entity_id = {
        share.entity_id: share for share in existing_result.scalars().all()
    }

    audit = AuditService(db)
    results: list[AdminBulkShareResult] = []
    created_count = 0
    updated_count = 0
    skipped_count = 0
    failed_count = 0
    changed_entity_ids: list[int] = []
    created_entity_ids: list[int] = []

    for entity_id in entity_ids:
        # Per-row savepoint so a single bad row (FK violation, constraint
        # error, audit failure) doesn't 500 the whole batch and discard the
        # `AdminBulkShareResult` rows we've already accumulated.
        try:
            async with db.begin_nested():
                entity, resolved_plural = await _resolve_entity(db, requested_entity_type, entity_id)
                if entity is None:
                    failed_count += 1
                    results.append(AdminBulkShareResult(
                        entity_id=entity_id,
                        status="failed",
                        detail=f"{requested_entity_type} {entity_id} not found",
                    ))
                    continue

                existing_share = existing_by_entity_id.get(entity_id)
                if existing_share is not None:
                    if existing_share.permission_level == request.permission_level:
                        skipped_count += 1
                        results.append(AdminBulkShareResult(
                            entity_id=entity_id,
                            status="skipped",
                            detail="User already has this permission",
                        ))
                        continue

                    old_permission = existing_share.permission_level
                    existing_share.entity_type = resolved_plural
                    existing_share.permission_level = request.permission_level
                    existing_share.shared_by_user_id = current_user.id
                    await audit.log_change(
                        entity_type=canonical_singular(resolved_plural),
                        entity_id=entity_id,
                        user_id=current_user.id,
                        action="share_permission_update",
                        changes=[{
                            "field": "permission_level",
                            "old": old_permission,
                            "new": request.permission_level,
                            "shared_with_user_id": request.shared_with_user_id,
                        }],
                    )
                    updated_count += 1
                    changed_entity_ids.append(entity_id)
                    results.append(AdminBulkShareResult(
                        entity_id=entity_id,
                        status="updated",
                        detail=f"Permission changed from {old_permission} to {request.permission_level}",
                    ))
                    continue

                share = EntityShare(
                    entity_type=resolved_plural,
                    entity_id=entity_id,
                    shared_with_user_id=request.shared_with_user_id,
                    shared_by_user_id=current_user.id,
                    permission_level=request.permission_level,
                )
                db.add(share)
                await db.flush()
                await audit.log_change(
                    entity_type=canonical_singular(resolved_plural),
                    entity_id=entity_id,
                    user_id=current_user.id,
                    action="share",
                    changes=[{
                        "field": "shared_with_user_id",
                        "old": None,
                        "new": request.shared_with_user_id,
                        "permission_level": request.permission_level,
                    }],
                )
                created_count += 1
                changed_entity_ids.append(entity_id)
                created_entity_ids.append(entity_id)
                results.append(AdminBulkShareResult(
                    entity_id=entity_id,
                    status="created",
                    detail="Share created",
                ))
        except SQLAlchemyError as exc:
            # Savepoint already rolled back this iteration. Remove any result
            # row we appended before the failure (the count-and-append happen
            # together inside the savepoint, but Python list mutations outside
            # the SQL session are not rolled back by begin_nested).
            if results and results[-1].entity_id == entity_id:
                last_status = results[-1].status
                results.pop()
                if last_status == "created":
                    created_count -= 1
                    if created_entity_ids and created_entity_ids[-1] == entity_id:
                        created_entity_ids.pop()
                    if changed_entity_ids and changed_entity_ids[-1] == entity_id:
                        changed_entity_ids.pop()
                elif last_status == "updated":
                    updated_count -= 1
                    if changed_entity_ids and changed_entity_ids[-1] == entity_id:
                        changed_entity_ids.pop()
                elif last_status == "skipped":
                    skipped_count -= 1
            failed_count += 1
            results.append(AdminBulkShareResult(
                entity_id=entity_id,
                status="failed",
                detail=f"Database error: {type(exc).__name__}",
            ))

    # Notify on both creates and updates: a permission upgrade (e.g. view →
    # assignee) is at least as impactful as a first-time grant, so silently
    # leaving the recipient in the dark for the upgrade path is wrong.
    if created_count > 0 or updated_count > 0:
        sharer_name = current_user.full_name or current_user.email
        entity_singular = canonical_singular(entity_plural)
        if request.permission_level == "assignee":
            notif_type = "record_assigned_to_you"
            verb = "assigned"
        else:
            notif_type = "entity_shared_with_you"
            verb = "shared"
        if created_count > 0 and updated_count > 0:
            title = (
                f"{sharer_name} {verb} {created_count} new and updated "
                f"{updated_count} existing {entity_singular} records"
            )
        elif created_count > 0:
            title = f"{sharer_name} {verb} {created_count} {entity_singular} records with you"
        else:
            title = (
                f"{sharer_name} updated your access to {updated_count} "
                f"{entity_singular} records"
            )
        # Deep-link to a representative record: prefer a newly-created one so
        # the recipient lands somewhere they didn't have access to before;
        # fall back to any changed record on an update-only batch.
        deep_link_id = created_entity_ids[0] if created_entity_ids else changed_entity_ids[0]
        await NotificationService(db).create_notification(
            user_id=target_user.id,
            type=notif_type,
            title=title,
            message=(
                f"{created_count + updated_count} {entity_singular} record(s) "
                f"now have updated access for you."
            ),
            entity_type=entity_plural,
            entity_id=deep_link_id,
        )

    await db.commit()
    if changed_entity_ids:
        invalidate_scope_cache(request.shared_with_user_id)

    return AdminBulkShareResponse(
        created=created_count,
        updated=updated_count,
        skipped=skipped_count,
        failed=failed_count,
        items=results,
    )


# ---------------------------------------------------------------------------
# Admin listing endpoint
# ---------------------------------------------------------------------------


class AdminShareItem(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    shared_with_user_id: int
    shared_with_user_name: str
    shared_with_user_email: str
    shared_by_user_id: int
    shared_by_user_name: str
    permission_level: str
    created_at: datetime
    # Null when the target record was hard-deleted, soft-deleted, or merged
    # away — the row still renders so the admin can revoke the stale share.
    entity_label: str | None = None
    entity_subtitle: str | None = None

    model_config = {"from_attributes": True}


class AdminShareListResponse(BaseModel):
    items: list[AdminShareItem]
    total: int
    page: int
    page_size: int


@router.get("/admin", response_model=AdminShareListResponse)
async def admin_list_shares(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    entity_type: str | None = Query(None),
    shared_with_user_id: int | None = Query(None),
    shared_by_user_id: int | None = Query(None),
    permission_level: str | None = Query(None),
    q: str | None = Query(
        None,
        min_length=1,
        max_length=200,
        description=(
            "Substring search across the recipient's name/email, the sharer's "
            "name, and the target entity's label (contact/lead full name + "
            "email, company name, lead/proposal company, proposal title)."
        ),
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List all EntityShare rows for admins."""
    if not current_user.is_superuser and data_scope.role_name != "admin":
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Only admins can access this endpoint",
        )

    SharedWith = aliased(User)
    SharedBy = aliased(User)
    # Polymorphic joins — one alias per entity_type. The join condition is
    # intentionally specific: `entity_id == X.id` alone would collide across
    # entity types since IDs are not namespaced.
    JoinedContact = aliased(Contact)
    ContactCompany = aliased(Company)  # contact.company_id → companies
    JoinedCompany = aliased(Company)
    JoinedLead = aliased(Lead)
    JoinedProposal = aliased(Proposal)
    ProposalContact = aliased(Contact)  # proposal.contact_id → contacts
    ProposalCompany = aliased(Company)  # proposal.company_id → companies

    base_query = (
        select(
            EntityShare.id,
            EntityShare.entity_type,
            EntityShare.entity_id,
            EntityShare.shared_with_user_id,
            SharedWith.full_name.label("shared_with_user_name"),
            SharedWith.email.label("shared_with_user_email"),
            EntityShare.shared_by_user_id,
            SharedBy.full_name.label("shared_by_user_name"),
            EntityShare.permission_level,
            EntityShare.created_at,
            JoinedContact.first_name.label("contact_first_name"),
            JoinedContact.last_name.label("contact_last_name"),
            JoinedContact.email.label("contact_email"),
            ContactCompany.name.label("contact_company_name"),
            JoinedCompany.name.label("company_name"),
            JoinedLead.first_name.label("lead_first_name"),
            JoinedLead.last_name.label("lead_last_name"),
            JoinedLead.company_name.label("lead_company_name"),
            JoinedLead.email.label("lead_email"),
            JoinedProposal.title.label("proposal_title"),
            ProposalContact.first_name.label("proposal_contact_first_name"),
            ProposalContact.last_name.label("proposal_contact_last_name"),
            ProposalCompany.name.label("proposal_company_name"),
        )
        .join(SharedWith, EntityShare.shared_with_user_id == SharedWith.id)
        .join(SharedBy, EntityShare.shared_by_user_id == SharedBy.id)
        # Soft-delete + merge predicates are part of the ON clause so a stale
        # share row falls through to the "Deleted/Merged X" rendering path
        # instead of resurrecting the tombstoned record's name.
        .outerjoin(
            JoinedContact,
            and_(
                EntityShare.entity_type.in_(entity_type_variants("contacts")),
                EntityShare.entity_id == JoinedContact.id,
                JoinedContact.deleted_at.is_(None),
                JoinedContact.merged_into_id.is_(None),
            ),
        )
        .outerjoin(
            ContactCompany,
            and_(
                JoinedContact.company_id == ContactCompany.id,
                ContactCompany.status != "merged",
                ContactCompany.merged_into_id.is_(None),
            ),
        )
        .outerjoin(
            JoinedCompany,
            and_(
                EntityShare.entity_type.in_(entity_type_variants("companies")),
                EntityShare.entity_id == JoinedCompany.id,
                JoinedCompany.status != "merged",
                JoinedCompany.merged_into_id.is_(None),
            ),
        )
        .outerjoin(
            JoinedLead,
            and_(
                EntityShare.entity_type.in_(entity_type_variants("leads")),
                EntityShare.entity_id == JoinedLead.id,
                JoinedLead.merged_into_id.is_(None),
            ),
        )
        .outerjoin(
            JoinedProposal,
            and_(
                EntityShare.entity_type.in_(entity_type_variants("proposals")),
                EntityShare.entity_id == JoinedProposal.id,
            ),
        )
        .outerjoin(
            ProposalContact,
            and_(
                JoinedProposal.contact_id == ProposalContact.id,
                ProposalContact.deleted_at.is_(None),
                ProposalContact.merged_into_id.is_(None),
            ),
        )
        .outerjoin(
            ProposalCompany,
            and_(
                JoinedProposal.company_id == ProposalCompany.id,
                ProposalCompany.status != "merged",
                ProposalCompany.merged_into_id.is_(None),
            ),
        )
    )

    if entity_type is not None:
        base_query = base_query.where(
            EntityShare.entity_type.in_(entity_type_variants(entity_type))
        )
    if shared_with_user_id is not None:
        base_query = base_query.where(EntityShare.shared_with_user_id == shared_with_user_id)
    if shared_by_user_id is not None:
        base_query = base_query.where(EntityShare.shared_by_user_id == shared_by_user_id)
    if permission_level is not None:
        base_query = base_query.where(EntityShare.permission_level == permission_level)

    if q is not None:
        # The search trims the term and treats whitespace-only queries as
        # absent so a stray space doesn't accidentally return zero rows.
        needle = q.strip()
        if needle:
            pattern = f"%{needle.lower()}%"
            base_query = base_query.where(
                or_(
                    func.lower(SharedWith.full_name).like(pattern),
                    func.lower(SharedWith.email).like(pattern),
                    func.lower(SharedBy.full_name).like(pattern),
                    func.lower(JoinedContact.first_name).like(pattern),
                    func.lower(JoinedContact.last_name).like(pattern),
                    func.lower(JoinedContact.email).like(pattern),
                    func.lower(ContactCompany.name).like(pattern),
                    func.lower(JoinedCompany.name).like(pattern),
                    func.lower(JoinedLead.first_name).like(pattern),
                    func.lower(JoinedLead.last_name).like(pattern),
                    func.lower(JoinedLead.email).like(pattern),
                    func.lower(JoinedLead.company_name).like(pattern),
                    func.lower(JoinedProposal.title).like(pattern),
                    func.lower(ProposalContact.first_name).like(pattern),
                    func.lower(ProposalContact.last_name).like(pattern),
                    func.lower(ProposalCompany.name).like(pattern),
                )
            )

    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    rows_result = await db.execute(
        base_query.order_by(EntityShare.created_at.desc()).offset(offset).limit(page_size)
    )
    rows = rows_result.all()

    items = [
        AdminShareItem(
            id=row.id,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            shared_with_user_id=row.shared_with_user_id,
            shared_with_user_name=row.shared_with_user_name,
            shared_with_user_email=row.shared_with_user_email,
            shared_by_user_id=row.shared_by_user_id,
            shared_by_user_name=row.shared_by_user_name,
            permission_level=row.permission_level,
            created_at=row.created_at,
            entity_label=_format_entity_label(row),
            entity_subtitle=_format_entity_subtitle(row),
        )
        for row in rows
    ]

    return AdminShareListResponse(items=items, total=total, page=page, page_size=page_size)


def _join_name(first: str | None, last: str | None) -> str | None:
    name = " ".join(p.strip() for p in (first, last) if p and p.strip())
    return name or None


def _format_entity_label(row) -> str | None:
    entity_type = row.entity_type
    if entity_type in entity_type_variants("contacts"):
        # Email is a defensible last resort: a contact with no name but a
        # populated email is still recognisable to the admin auditing shares.
        return (
            _join_name(row.contact_first_name, row.contact_last_name)
            or row.contact_email
        )
    if entity_type in entity_type_variants("companies"):
        return row.company_name
    if entity_type in entity_type_variants("leads"):
        return _join_name(row.lead_first_name, row.lead_last_name) or row.lead_company_name
    if entity_type in entity_type_variants("proposals"):
        return row.proposal_title
    return None


def _format_entity_subtitle(row) -> str | None:
    entity_type = row.entity_type
    if entity_type in entity_type_variants("contacts"):
        parts = [row.contact_company_name, row.contact_email]
    elif entity_type in entity_type_variants("leads"):
        parts = [row.lead_company_name, row.lead_email]
    elif entity_type in entity_type_variants("proposals"):
        parts = [
            row.proposal_company_name,
            _join_name(row.proposal_contact_first_name, row.proposal_contact_last_name),
        ]
    else:
        return None

    filtered = [p for p in parts if p]
    return " • ".join(filtered) if filtered else None

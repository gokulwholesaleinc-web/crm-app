"""Contact API routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.ai.embedding_hooks import (
    build_contact_embedding_content,
    delete_entity_embedding,
    store_entity_embedding,
)
from src.audit.utils import (
    audit_entity_create,
    audit_entity_delete,
    audit_entity_update,
    snapshot_entity,
)
from src.contacts.models import ContactEmailAlias
from src.contacts.schemas import (
    ContactCreate,
    ContactEmailAliasCreate,
    ContactEmailAliasResponse,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
    TagBrief,
)
from src.contacts.service import ContactService
from src.core.constants import ENTITY_TYPE_CONTACTS, EntityNames, HTTPStatus
from src.core.data_scope import DataScope, check_record_access_or_shared, get_data_scope
from src.core.router_utils import (
    CurrentUser,
    DBSession,
    build_list_responses_with_tags,
    build_response_with_tags,
    calculate_pages,
    check_ownership,
    effective_owner_id,
    get_entity_or_404,
    parse_json_filters,
    parse_tag_ids,
)
from src.events.service import CONTACT_CREATED, CONTACT_UPDATED, emit
from src.notifications.service import notify_on_assignment

logger = logging.getLogger(__name__)


async def _store_embedding_in_background(entity_type: str, entity_id: int, content: str):
    """Store embedding in a background task with its own DB session."""
    from src.database import async_session_maker
    async with async_session_maker() as session:
        try:
            await store_entity_embedding(session, entity_type, entity_id, content)
            await session.commit()
        except Exception as e:
            logger.warning("Background embedding storage failed for %s/%s: %s", entity_type, entity_id, e)


router = APIRouter(prefix="/api/contacts", tags=["contacts"])


async def _build_contact_response(service: ContactService, contact) -> ContactResponse:
    return await build_response_with_tags(service, contact, ContactResponse, TagBrief)


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    company_id: int | None = None,
    status: str | None = None,
    owner_id: int | None = None,
    tag_ids: str | None = None,
    filters: str | None = None,
):
    """List contacts with pagination and filters."""
    service = ContactService(db)

    contacts, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        company_id=company_id,
        status=status,
        owner_id=effective_owner_id(data_scope, owner_id),
        tag_ids=parse_tag_ids(tag_ids),
        filters=parse_json_filters(filters),
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_CONTACTS),
    )

    tags_map = await service.get_tags_for_entities([c.id for c in contacts])

    return ContactListResponse(
        items=build_list_responses_with_tags(contacts, tags_map, ContactResponse, TagBrief),
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=ContactResponse, status_code=HTTPStatus.CREATED)
async def create_contact(
    contact_data: ContactCreate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    background_tasks: BackgroundTasks,
):
    """Create a new contact."""
    service = ContactService(db)
    contact = await service.create(contact_data, current_user.id)

    # Generate embedding for semantic search (background)
    try:
        company_name = contact.company.name if contact.company else None
        content = build_contact_embedding_content(contact, company_name)
        background_tasks.add_task(_store_embedding_in_background, "contact", contact.id, content)
    except Exception as e:
        logger.warning("Failed to prepare embedding: %s", e)

    ip_address = request.client.host if request.client else None
    await audit_entity_create(db, "contact", contact.id, current_user.id, ip_address)

    await emit(CONTACT_CREATED, {
        "entity_id": contact.id,
        "entity_type": "contact",
        "user_id": current_user.id,
        "data": {"first_name": contact.first_name, "last_name": contact.last_name, "email": contact.email, "status": contact.status},
    })

    if contact.owner_id and contact.owner_id != current_user.id:
        await notify_on_assignment(db, contact.owner_id, "contacts", contact.id, contact.full_name)

    return await _build_contact_response(service, contact)


@router.get("/{contact_id}/payment-summary")
async def get_contact_payment_summary(
    contact_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Get payment summary for a contact via their StripeCustomer link."""
    service = ContactService(db)
    contact = await get_entity_or_404(service, contact_id, EntityNames.CONTACT)
    check_record_access_or_shared(
        contact, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_CONTACTS),
    )
    return await service.get_payment_summary(contact_id)


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Get a contact by ID."""
    service = ContactService(db)
    contact = await get_entity_or_404(service, contact_id, EntityNames.CONTACT)
    check_record_access_or_shared(
        contact, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_CONTACTS),
    )
    return await _build_contact_response(service, contact)


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: int,
    contact_data: ContactUpdate,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
    background_tasks: BackgroundTasks,
):
    """Update a contact."""
    service = ContactService(db)
    contact = await get_entity_or_404(service, contact_id, EntityNames.CONTACT)
    check_ownership(contact, current_user, EntityNames.CONTACT)

    old_owner_id = contact.owner_id

    update_fields = list(contact_data.model_dump(exclude_unset=True).keys())
    old_data = snapshot_entity(contact, update_fields)

    updated_contact = await service.update(contact, contact_data, current_user.id)

    # Update embedding for semantic search (background)
    try:
        company_name = updated_contact.company.name if updated_contact.company else None
        content = build_contact_embedding_content(updated_contact, company_name)
        background_tasks.add_task(_store_embedding_in_background, "contact", updated_contact.id, content)
    except Exception as e:
        logger.warning("Failed to prepare embedding: %s", e)

    new_data = snapshot_entity(updated_contact, update_fields)
    ip_address = request.client.host if request.client else None
    await audit_entity_update(db, "contact", updated_contact.id, current_user.id, old_data, new_data, ip_address)

    await emit(CONTACT_UPDATED, {
        "entity_id": updated_contact.id,
        "entity_type": "contact",
        "user_id": current_user.id,
        "data": {"first_name": updated_contact.first_name, "last_name": updated_contact.last_name, "email": updated_contact.email, "status": updated_contact.status},
    })

    if updated_contact.owner_id and updated_contact.owner_id != old_owner_id:
        await notify_on_assignment(db, updated_contact.owner_id, "contacts", updated_contact.id, updated_contact.full_name)

    return await _build_contact_response(service, updated_contact)


@router.delete("/{contact_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_contact(
    contact_id: int,
    request: Request,
    current_user: CurrentUser,
    db: DBSession,
):
    """Soft-delete a contact.

    Contacts are never hard-deleted: they anchor AR ledger entries,
    invoices, activities, and email threads. Setting ``deleted_at`` + a
    status of ``archived`` hides the row from list views while preserving
    every reference that points at it. Per project rule
    ``feedback_delete_sales_only.md``.
    """
    service = ContactService(db)
    contact = await get_entity_or_404(service, contact_id, EntityNames.CONTACT)
    check_ownership(contact, current_user, EntityNames.CONTACT)

    ip_address = request.client.host if request.client else None
    await audit_entity_delete(db, "contact", contact.id, current_user.id, ip_address)

    # Remove the semantic-search embedding so archived contacts no longer
    # surface in AI-assistant suggestions, but leave the row itself in place.
    await delete_entity_embedding(db, "contact", contact.id)

    await service.soft_delete(contact)


# ---------------------------------------------------------------------------
# Email alias endpoints
# ---------------------------------------------------------------------------

@router.get("/{contact_id}/aliases", response_model=list[ContactEmailAliasResponse])
async def list_aliases(
    contact_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """List all email aliases for a contact.

    Uses the same access check as GET /{contact_id} so share recipients can
    read aliases on contacts that have been shared with them.
    """
    service = ContactService(db)
    contact = await get_entity_or_404(service, contact_id, EntityNames.CONTACT)
    check_record_access_or_shared(
        contact, current_user, data_scope.role_name,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_CONTACTS),
    )

    result = await db.execute(
        select(ContactEmailAlias)
        .where(ContactEmailAlias.contact_id == contact_id)
        .order_by(ContactEmailAlias.created_at)
    )
    return result.scalars().all()


@router.post(
    "/{contact_id}/aliases",
    response_model=ContactEmailAliasResponse,
    status_code=201,
)
async def add_alias(
    contact_id: int,
    body: ContactEmailAliasCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Add an email alias to a contact. 409 if the address is already claimed."""
    service = ContactService(db)
    contact = await get_entity_or_404(service, contact_id, EntityNames.CONTACT)
    check_ownership(contact, current_user, EntityNames.CONTACT)

    alias = ContactEmailAlias(
        contact_id=contact_id,
        email=body.email,
        label=body.label,
    )
    db.add(alias)
    try:
        await db.commit()
        await db.refresh(alias)
    except IntegrityError as exc:
        await db.rollback()
        # Narrow to unique-constraint violations (SQLSTATE 23505). Other
        # IntegrityErrors (e.g. unexpected FK failures) should surface as 500
        # so the caller isn't misled by a 409.
        orig = getattr(exc, "orig", None)
        pgcode = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
        if pgcode == "23505":
            raise HTTPException(status_code=409, detail="Email address already exists as an alias")
        raise
    return alias


@router.delete("/{contact_id}/aliases/{alias_id}", status_code=204)
async def delete_alias(
    contact_id: int,
    alias_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Remove an email alias from a contact."""
    service = ContactService(db)
    contact = await get_entity_or_404(service, contact_id, EntityNames.CONTACT)
    check_ownership(contact, current_user, EntityNames.CONTACT)

    result = await db.execute(
        select(ContactEmailAlias).where(
            ContactEmailAlias.id == alias_id,
            ContactEmailAlias.contact_id == contact_id,
        )
    )
    alias = result.scalar_one_or_none()
    if alias is None:
        raise HTTPException(status_code=404, detail="Alias not found")

    await db.delete(alias)
    await db.commit()

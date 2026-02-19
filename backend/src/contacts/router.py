"""Contact API routes."""

import logging
from typing import Annotated, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from src.core.constants import HTTPStatus, EntityNames, ENTITY_TYPE_CONTACTS
from src.core.router_utils import (
    DBSession,
    CurrentUser,
    parse_tag_ids,
    get_entity_or_404,
    calculate_pages,
    check_ownership,
)
from src.core.data_scope import DataScope, get_data_scope, check_record_access_or_shared
from src.contacts.schemas import (
    ContactCreate,
    ContactUpdate,
    ContactResponse,
    ContactListResponse,
    TagBrief,
)
from src.contacts.service import ContactService
from src.ai.embedding_hooks import (
    store_entity_embedding,
    delete_entity_embedding,
    build_contact_embedding_content,
)
from src.audit.utils import audit_entity_create, audit_entity_update, audit_entity_delete, snapshot_entity
from src.events.service import emit, CONTACT_CREATED, CONTACT_UPDATED
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
    """Build a ContactResponse with tags."""
    tags = await service.get_tags(contact.id)
    response_dict = ContactResponse.model_validate(contact).model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]
    return ContactResponse(**response_dict)


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    company_id: Optional[int] = None,
    status: Optional[str] = None,
    owner_id: Optional[int] = None,
    tag_ids: Optional[str] = None,
    filters: Optional[str] = None,
):
    """List contacts with pagination and filters."""
    import json as _json
    from fastapi import HTTPException
    parsed_filters = None
    if filters:
        try:
            parsed_filters = _json.loads(filters)
        except _json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON filter format")

    if data_scope.can_see_all():
        effective_owner_id = owner_id
    else:
        effective_owner_id = data_scope.owner_id

    service = ContactService(db)

    contacts, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        company_id=company_id,
        status=status,
        owner_id=effective_owner_id,
        tag_ids=parse_tag_ids(tag_ids),
        filters=parsed_filters,
        shared_entity_ids=data_scope.get_shared_ids(ENTITY_TYPE_CONTACTS),
    )

    # Bulk-load tags in a single query to avoid N+1
    entity_ids = [contact.id for contact in contacts]
    tags_map = await service.get_tags_for_entities(entity_ids)

    contact_responses = []
    for contact in contacts:
        response_dict = ContactResponse.model_validate(contact).model_dump()
        response_dict["tags"] = [TagBrief.model_validate(t) for t in tags_map.get(contact.id, [])]
        contact_responses.append(ContactResponse(**response_dict))

    return ContactListResponse(
        items=contact_responses,
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
    """Delete a contact."""
    service = ContactService(db)
    contact = await get_entity_or_404(service, contact_id, EntityNames.CONTACT)
    check_ownership(contact, current_user, EntityNames.CONTACT)

    ip_address = request.client.host if request.client else None
    await audit_entity_delete(db, "contact", contact.id, current_user.id, ip_address)

    # Delete embedding before deleting entity
    await delete_entity_embedding(db, "contact", contact.id)

    await service.delete(contact)

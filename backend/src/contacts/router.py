"""Contact API routes."""

import logging
from typing import Optional
from fastapi import APIRouter, Query
from src.core.constants import HTTPStatus, EntityNames
from src.core.router_utils import (
    DBSession,
    CurrentUser,
    parse_tag_ids,
    get_entity_or_404,
    calculate_pages,
    check_ownership,
)
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

logger = logging.getLogger(__name__)

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
    parsed_filters = _json.loads(filters) if filters else None

    # Auto-scope to current user's data by default
    effective_owner_id = owner_id
    if effective_owner_id is None:
        effective_owner_id = current_user.id

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
    )

    contact_responses = [
        await _build_contact_response(service, contact) for contact in contacts
    ]

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
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new contact."""
    service = ContactService(db)
    contact = await service.create(contact_data, current_user.id)

    # Generate embedding for semantic search
    try:
        company_name = contact.company.name if contact.company else None
        content = build_contact_embedding_content(contact, company_name)
        await store_entity_embedding(db, "contact", contact.id, content)
    except Exception as e:
        logger.warning("Failed to store embedding: %s", e)

    return await _build_contact_response(service, contact)


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a contact by ID."""
    service = ContactService(db)
    contact = await get_entity_or_404(service, contact_id, EntityNames.CONTACT)
    return await _build_contact_response(service, contact)


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: int,
    contact_data: ContactUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a contact."""
    service = ContactService(db)
    contact = await get_entity_or_404(service, contact_id, EntityNames.CONTACT)
    check_ownership(contact, current_user, EntityNames.CONTACT)
    updated_contact = await service.update(contact, contact_data, current_user.id)

    # Update embedding for semantic search
    try:
        company_name = updated_contact.company.name if updated_contact.company else None
        content = build_contact_embedding_content(updated_contact, company_name)
        await store_entity_embedding(db, "contact", updated_contact.id, content)
    except Exception as e:
        logger.warning("Failed to store embedding: %s", e)

    return await _build_contact_response(service, updated_contact)


@router.delete("/{contact_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_contact(
    contact_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a contact."""
    service = ContactService(db)
    contact = await get_entity_or_404(service, contact_id, EntityNames.CONTACT)
    check_ownership(contact, current_user, EntityNames.CONTACT)

    # Delete embedding before deleting entity
    await delete_entity_embedding(db, "contact", contact.id)

    await service.delete(contact)

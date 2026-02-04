"""Contact API routes."""

from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import get_current_active_user
from src.contacts.models import Contact
from src.contacts.schemas import (
    ContactCreate,
    ContactUpdate,
    ContactResponse,
    ContactListResponse,
    TagBrief,
)
from src.contacts.service import ContactService

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    company_id: Optional[int] = None,
    status: Optional[str] = None,
    owner_id: Optional[int] = None,
    tag_ids: Optional[str] = None,  # Comma-separated list
):
    """List contacts with pagination and filters."""
    service = ContactService(db)

    # Parse tag_ids
    parsed_tag_ids = None
    if tag_ids:
        parsed_tag_ids = [int(x) for x in tag_ids.split(",")]

    contacts, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        company_id=company_id,
        status=status,
        owner_id=owner_id,
        tag_ids=parsed_tag_ids,
    )

    # Fetch tags for each contact
    contact_responses = []
    for contact in contacts:
        tags = await service.get_contact_tags(contact.id)
        contact_dict = ContactResponse.model_validate(contact).model_dump()
        contact_dict["tags"] = [TagBrief.model_validate(t) for t in tags]
        contact_responses.append(ContactResponse(**contact_dict))

    pages = (total + page_size - 1) // page_size

    return ContactListResponse(
        items=contact_responses,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    contact_data: ContactCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new contact."""
    service = ContactService(db)
    contact = await service.create(contact_data, current_user.id)

    tags = await service.get_contact_tags(contact.id)
    response = ContactResponse.model_validate(contact)
    response_dict = response.model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]

    return ContactResponse(**response_dict)


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get a contact by ID."""
    service = ContactService(db)
    contact = await service.get_by_id(contact_id)

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    tags = await service.get_contact_tags(contact.id)
    response = ContactResponse.model_validate(contact)
    response_dict = response.model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]

    return ContactResponse(**response_dict)


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: int,
    contact_data: ContactUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update a contact."""
    service = ContactService(db)
    contact = await service.get_by_id(contact_id)

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    updated_contact = await service.update(contact, contact_data, current_user.id)

    tags = await service.get_contact_tags(updated_contact.id)
    response = ContactResponse.model_validate(updated_contact)
    response_dict = response.model_dump()
    response_dict["tags"] = [TagBrief.model_validate(t) for t in tags]

    return ContactResponse(**response_dict)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a contact."""
    service = ContactService(db)
    contact = await service.get_by_id(contact_id)

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    await service.delete(contact)

"""Campaign API routes."""

from typing import Annotated, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import get_current_active_user
from src.campaigns.models import Campaign
from src.campaigns.schemas import (
    CampaignCreate,
    CampaignUpdate,
    CampaignResponse,
    CampaignListResponse,
    CampaignMemberResponse,
    CampaignMemberUpdate,
    AddMembersRequest,
    CampaignStats,
)
from src.campaigns.service import CampaignService, CampaignMemberService

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    campaign_type: Optional[str] = None,
    status: Optional[str] = None,
    owner_id: Optional[int] = None,
):
    """List campaigns with pagination and filters."""
    service = CampaignService(db)

    campaigns, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        campaign_type=campaign_type,
        status=status,
        owner_id=owner_id,
    )

    pages = (total + page_size - 1) // page_size

    return CampaignListResponse(
        items=[CampaignResponse.model_validate(c) for c in campaigns],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    campaign_data: CampaignCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new campaign."""
    service = CampaignService(db)
    campaign = await service.create(campaign_data, current_user.id)
    return CampaignResponse.model_validate(campaign)


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get a campaign by ID."""
    service = CampaignService(db)
    campaign = await service.get_by_id(campaign_id)

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return CampaignResponse.model_validate(campaign)


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int,
    campaign_data: CampaignUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update a campaign."""
    service = CampaignService(db)
    campaign = await service.get_by_id(campaign_id)

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    updated_campaign = await service.update(campaign, campaign_data, current_user.id)
    return CampaignResponse.model_validate(updated_campaign)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a campaign."""
    service = CampaignService(db)
    campaign = await service.get_by_id(campaign_id)

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    await service.delete(campaign)


@router.get("/{campaign_id}/stats", response_model=CampaignStats)
async def get_campaign_stats(
    campaign_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get campaign statistics."""
    service = CampaignService(db)
    campaign = await service.get_by_id(campaign_id)

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    stats = await service.get_campaign_stats(campaign_id)
    return CampaignStats(**stats)


# Campaign Members endpoints
@router.get("/{campaign_id}/members", response_model=List[CampaignMemberResponse])
async def list_campaign_members(
    campaign_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """List members of a campaign."""
    member_service = CampaignMemberService(db)
    members, _ = await member_service.get_campaign_members(
        campaign_id=campaign_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    return [CampaignMemberResponse.model_validate(m) for m in members]


@router.post("/{campaign_id}/members")
async def add_campaign_members(
    campaign_id: int,
    request: AddMembersRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Add members to a campaign."""
    # Verify campaign exists
    campaign_service = CampaignService(db)
    campaign = await campaign_service.get_by_id(campaign_id)

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    member_service = CampaignMemberService(db)
    added = await member_service.add_members_bulk(
        campaign_id=campaign_id,
        member_type=request.member_type,
        member_ids=request.member_ids,
    )

    return {"added": added, "message": f"Added {added} members to campaign"}


@router.patch("/{campaign_id}/members/{member_id}", response_model=CampaignMemberResponse)
async def update_campaign_member(
    campaign_id: int,
    member_id: int,
    member_data: CampaignMemberUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update a campaign member."""
    member_service = CampaignMemberService(db)
    member = await member_service.get_by_id(member_id)

    if not member or member.campaign_id != campaign_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign member not found",
        )

    updated_member = await member_service.update_member(member, member_data)
    return CampaignMemberResponse.model_validate(updated_member)


@router.delete("/{campaign_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_campaign_member(
    campaign_id: int,
    member_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Remove a member from a campaign."""
    member_service = CampaignMemberService(db)
    member = await member_service.get_by_id(member_id)

    if not member or member.campaign_id != campaign_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign member not found",
        )

    await member_service.remove_member(member)

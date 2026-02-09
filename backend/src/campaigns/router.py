"""Campaign API routes."""

from typing import Optional, List
from fastapi import APIRouter, Query
from src.core.constants import HTTPStatus, EntityNames
from src.core.router_utils import (
    DBSession,
    CurrentUser,
    get_entity_or_404,
    calculate_pages,
    raise_not_found,
    check_ownership,
)
from src.campaigns.schemas import (
    CampaignCreate,
    CampaignUpdate,
    CampaignResponse,
    CampaignListResponse,
    CampaignMemberResponse,
    CampaignMemberUpdate,
    AddMembersRequest,
    CampaignStats,
    EmailTemplateCreate,
    EmailTemplateUpdate,
    EmailTemplateResponse,
    EmailCampaignStepCreate,
    EmailCampaignStepUpdate,
    EmailCampaignStepResponse,
)
from src.campaigns.service import (
    CampaignService,
    CampaignMemberService,
    EmailTemplateService,
    EmailCampaignStepService,
)

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


# =========================================================================
# Email Template endpoints (MUST be before /{campaign_id} routes)
# =========================================================================

@router.post("/templates", response_model=EmailTemplateResponse, status_code=HTTPStatus.CREATED)
async def create_email_template(
    template_data: EmailTemplateCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new email template."""
    service = EmailTemplateService(db)
    template = await service.create_template(template_data, current_user.id)
    return EmailTemplateResponse.model_validate(template)


@router.get("/templates", response_model=List[EmailTemplateResponse])
async def list_email_templates(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
):
    """List email templates."""
    service = EmailTemplateService(db)
    templates, _ = await service.get_list(page=page, page_size=page_size, category=category)
    return [EmailTemplateResponse.model_validate(t) for t in templates]


@router.get("/templates/{template_id}", response_model=EmailTemplateResponse)
async def get_email_template(
    template_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get an email template by ID."""
    service = EmailTemplateService(db)
    template = await service.get_by_id(template_id)
    if not template:
        raise_not_found("Email template", template_id)
    return EmailTemplateResponse.model_validate(template)


@router.put("/templates/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template(
    template_id: int,
    template_data: EmailTemplateUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update an email template."""
    service = EmailTemplateService(db)
    template = await service.get_by_id(template_id)
    if not template:
        raise_not_found("Email template", template_id)
    updated = await service.update_template(template, template_data)
    return EmailTemplateResponse.model_validate(updated)


@router.delete("/templates/{template_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_email_template(
    template_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete an email template."""
    service = EmailTemplateService(db)
    template = await service.get_by_id(template_id)
    if not template:
        raise_not_found("Email template", template_id)
    await service.delete_template(template)


# =========================================================================
# Campaign CRUD endpoints
# =========================================================================

@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    campaign_type: Optional[str] = None,
    status: Optional[str] = None,
    owner_id: Optional[int] = None,
):
    """List campaigns with pagination and filters."""
    # Auto-scope to current user's data by default
    effective_owner_id = owner_id
    if effective_owner_id is None:
        effective_owner_id = current_user.id

    service = CampaignService(db)

    campaigns, total = await service.get_list(
        page=page,
        page_size=page_size,
        search=search,
        campaign_type=campaign_type,
        status=status,
        owner_id=effective_owner_id,
    )

    return CampaignListResponse(
        items=[CampaignResponse.model_validate(c) for c in campaigns],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=CampaignResponse, status_code=HTTPStatus.CREATED)
async def create_campaign(
    campaign_data: CampaignCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new campaign."""
    service = CampaignService(db)
    campaign = await service.create(campaign_data, current_user.id)
    return CampaignResponse.model_validate(campaign)


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a campaign by ID."""
    service = CampaignService(db)
    campaign = await get_entity_or_404(service, campaign_id, EntityNames.CAMPAIGN)
    return CampaignResponse.model_validate(campaign)


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: int,
    campaign_data: CampaignUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a campaign."""
    service = CampaignService(db)
    campaign = await get_entity_or_404(service, campaign_id, EntityNames.CAMPAIGN)
    check_ownership(campaign, current_user, EntityNames.CAMPAIGN)
    updated_campaign = await service.update(campaign, campaign_data, current_user.id)
    return CampaignResponse.model_validate(updated_campaign)


@router.delete("/{campaign_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_campaign(
    campaign_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a campaign."""
    service = CampaignService(db)
    campaign = await get_entity_or_404(service, campaign_id, EntityNames.CAMPAIGN)
    check_ownership(campaign, current_user, EntityNames.CAMPAIGN)
    await service.delete(campaign)


@router.get("/{campaign_id}/stats", response_model=CampaignStats)
async def get_campaign_stats(
    campaign_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get campaign statistics."""
    service = CampaignService(db)
    campaign = await get_entity_or_404(service, campaign_id, EntityNames.CAMPAIGN)
    stats = await service.get_campaign_stats(campaign_id)
    return CampaignStats(**stats)


# =========================================================================
# Campaign Members endpoints
# =========================================================================

@router.get("/{campaign_id}/members", response_model=List[CampaignMemberResponse])
async def list_campaign_members(
    campaign_id: int,
    current_user: CurrentUser,
    db: DBSession,
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
    current_user: CurrentUser,
    db: DBSession,
):
    """Add members to a campaign."""
    campaign_service = CampaignService(db)
    await get_entity_or_404(campaign_service, campaign_id, EntityNames.CAMPAIGN)

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
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a campaign member."""
    member_service = CampaignMemberService(db)
    member = await member_service.get_by_id(member_id)

    if not member or member.campaign_id != campaign_id:
        raise_not_found(EntityNames.CAMPAIGN_MEMBER, member_id)

    updated_member = await member_service.update_member(member, member_data)
    return CampaignMemberResponse.model_validate(updated_member)


@router.delete("/{campaign_id}/members/{member_id}", status_code=HTTPStatus.NO_CONTENT)
async def remove_campaign_member(
    campaign_id: int,
    member_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Remove a member from a campaign."""
    member_service = CampaignMemberService(db)
    member = await member_service.get_by_id(member_id)

    if not member or member.campaign_id != campaign_id:
        raise_not_found(EntityNames.CAMPAIGN_MEMBER, member_id)

    await member_service.remove_member(member)


# =========================================================================
# Email Campaign Step endpoints
# =========================================================================

@router.post("/{campaign_id}/steps", response_model=EmailCampaignStepResponse, status_code=HTTPStatus.CREATED)
async def add_campaign_step(
    campaign_id: int,
    step_data: EmailCampaignStepCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Add a step to a campaign sequence."""
    campaign_service = CampaignService(db)
    await get_entity_or_404(campaign_service, campaign_id, EntityNames.CAMPAIGN)

    step_service = EmailCampaignStepService(db)
    step = await step_service.create_step(campaign_id, step_data)
    return EmailCampaignStepResponse.model_validate(step)


@router.get("/{campaign_id}/steps", response_model=List[EmailCampaignStepResponse])
async def get_campaign_steps(
    campaign_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get all steps for a campaign."""
    campaign_service = CampaignService(db)
    await get_entity_or_404(campaign_service, campaign_id, EntityNames.CAMPAIGN)

    step_service = EmailCampaignStepService(db)
    steps = await step_service.get_steps(campaign_id)
    return [EmailCampaignStepResponse.model_validate(s) for s in steps]


@router.put("/{campaign_id}/steps/{step_id}", response_model=EmailCampaignStepResponse)
async def update_campaign_step(
    campaign_id: int,
    step_id: int,
    step_data: EmailCampaignStepUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a campaign step."""
    step_service = EmailCampaignStepService(db)
    step = await step_service.get_by_id(step_id)
    if not step or step.campaign_id != campaign_id:
        raise_not_found("Campaign step", step_id)
    updated = await step_service.update_step(step, step_data)
    return EmailCampaignStepResponse.model_validate(updated)


@router.delete("/{campaign_id}/steps/{step_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_campaign_step(
    campaign_id: int,
    step_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a campaign step."""
    step_service = EmailCampaignStepService(db)
    step = await step_service.get_by_id(step_id)
    if not step or step.campaign_id != campaign_id:
        raise_not_found("Campaign step", step_id)
    await step_service.delete_step(step)


@router.post("/{campaign_id}/execute")
async def execute_campaign(
    campaign_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Trigger campaign execution (set status to in_progress)."""
    service = CampaignService(db)
    campaign = await get_entity_or_404(service, campaign_id, EntityNames.CAMPAIGN)
    campaign.status = "in_progress"
    await db.flush()
    await db.refresh(campaign)
    return {"message": "Campaign execution started", "status": campaign.status}

"""Campaign service layer."""

from typing import Optional, List, Tuple, Dict
from sqlalchemy import select, func
from src.campaigns.models import Campaign, CampaignMember, EmailTemplate, EmailCampaignStep
from src.campaigns.schemas import (
    CampaignCreate,
    CampaignUpdate,
    CampaignMemberCreate,
    CampaignMemberUpdate,
    EmailTemplateCreate,
    EmailTemplateUpdate,
    EmailCampaignStepCreate,
    EmailCampaignStepUpdate,
)
from src.core.base_service import CRUDService, BaseService
from src.core.constants import DEFAULT_PAGE_SIZE


class CampaignService(CRUDService[Campaign, CampaignCreate, CampaignUpdate]):
    """Service for Campaign CRUD operations."""

    model = Campaign
    # Campaigns don't have tag_ids in their schemas
    create_exclude_fields: set = set()
    update_exclude_fields: set = set()

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        search: Optional[str] = None,
        campaign_type: Optional[str] = None,
        status: Optional[str] = None,
        owner_id: Optional[int] = None,
    ) -> Tuple[List[Campaign], int]:
        """Get paginated list of campaigns with filters."""
        query = select(Campaign)

        if search:
            query = query.where(Campaign.name.ilike(f"%{search}%"))

        if campaign_type:
            query = query.where(Campaign.campaign_type == campaign_type)

        if status:
            query = query.where(Campaign.status == status)

        if owner_id:
            query = query.where(Campaign.owner_id == owner_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Campaign.created_at.desc())

        result = await self.db.execute(query)
        campaigns = list(result.scalars().all())

        return campaigns, total

    async def get_campaign_stats(self, campaign_id: int) -> Dict:
        """Get campaign statistics."""
        # Count by status
        result = await self.db.execute(
            select(
                CampaignMember.status,
                func.count(CampaignMember.id).label("count")
            )
            .where(CampaignMember.campaign_id == campaign_id)
            .group_by(CampaignMember.status)
        )
        status_counts = {row.status: row.count for row in result.all()}

        total = sum(status_counts.values())
        pending = status_counts.get("pending", 0)
        sent = status_counts.get("sent", 0)
        responded = status_counts.get("responded", 0)
        converted = status_counts.get("converted", 0)

        response_rate = None
        if sent > 0:
            response_rate = (responded / sent) * 100

        conversion_rate = None
        if responded > 0:
            conversion_rate = (converted / responded) * 100

        return {
            "total_members": total,
            "pending": pending,
            "sent": sent,
            "responded": responded,
            "converted": converted,
            "response_rate": response_rate,
            "conversion_rate": conversion_rate,
        }


class CampaignMemberService(BaseService[CampaignMember]):
    """Service for CampaignMember operations."""

    model = CampaignMember

    async def get_campaign_members(
        self,
        campaign_id: int,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[CampaignMember], int]:
        """Get members of a campaign."""
        query = select(CampaignMember).where(CampaignMember.campaign_id == campaign_id)

        if status:
            query = query.where(CampaignMember.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        members = list(result.scalars().all())

        return members, total

    async def add_member(self, data: CampaignMemberCreate) -> CampaignMember:
        """Add a member to a campaign."""
        member = CampaignMember(**data.model_dump())
        self.db.add(member)
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def add_members_bulk(
        self,
        campaign_id: int,
        member_type: str,
        member_ids: List[int],
    ) -> int:
        """Add multiple members to a campaign."""
        added = 0
        for member_id in member_ids:
            # Check if already exists
            result = await self.db.execute(
                select(CampaignMember).where(
                    CampaignMember.campaign_id == campaign_id,
                    CampaignMember.member_type == member_type,
                    CampaignMember.member_id == member_id,
                )
            )
            existing = result.scalar_one_or_none()

            if not existing:
                member = CampaignMember(
                    campaign_id=campaign_id,
                    member_type=member_type,
                    member_id=member_id,
                )
                self.db.add(member)
                added += 1

        await self.db.flush()
        return added

    async def update_member(
        self,
        member: CampaignMember,
        data: CampaignMemberUpdate,
    ) -> CampaignMember:
        """Update a campaign member."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(member, field, value)
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def remove_member(self, member: CampaignMember) -> None:
        """Remove a member from a campaign."""
        await self.db.delete(member)
        await self.db.flush()


class EmailTemplateService(BaseService[EmailTemplate]):
    """Service for EmailTemplate operations."""

    model = EmailTemplate

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        category: Optional[str] = None,
    ) -> Tuple[List[EmailTemplate], int]:
        """Get paginated list of email templates."""
        query = select(EmailTemplate)

        if category:
            query = query.where(EmailTemplate.category == category)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(EmailTemplate.created_at.desc())

        result = await self.db.execute(query)
        templates = list(result.scalars().all())

        return templates, total

    async def create_template(self, data: EmailTemplateCreate, user_id: int) -> EmailTemplate:
        """Create a new email template."""
        template = EmailTemplate(**data.model_dump(), created_by_id=user_id)
        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def update_template(self, template: EmailTemplate, data: EmailTemplateUpdate) -> EmailTemplate:
        """Update an email template."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(template, field, value)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def delete_template(self, template: EmailTemplate) -> None:
        """Delete an email template."""
        await self.db.delete(template)
        await self.db.flush()


class EmailCampaignStepService(BaseService[EmailCampaignStep]):
    """Service for EmailCampaignStep operations."""

    model = EmailCampaignStep

    async def get_steps(self, campaign_id: int) -> List[EmailCampaignStep]:
        """Get all steps for a campaign, ordered by step_order."""
        result = await self.db.execute(
            select(EmailCampaignStep)
            .where(EmailCampaignStep.campaign_id == campaign_id)
            .order_by(EmailCampaignStep.step_order)
        )
        return list(result.scalars().all())

    async def create_step(self, campaign_id: int, data: EmailCampaignStepCreate) -> EmailCampaignStep:
        """Add a step to a campaign sequence."""
        step = EmailCampaignStep(campaign_id=campaign_id, **data.model_dump())
        self.db.add(step)
        await self.db.flush()
        await self.db.refresh(step)
        return step

    async def update_step(self, step: EmailCampaignStep, data: EmailCampaignStepUpdate) -> EmailCampaignStep:
        """Update a campaign step."""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(step, field, value)
        await self.db.flush()
        await self.db.refresh(step)
        return step

    async def delete_step(self, step: EmailCampaignStep) -> None:
        """Delete a campaign step."""
        await self.db.delete(step)
        await self.db.flush()

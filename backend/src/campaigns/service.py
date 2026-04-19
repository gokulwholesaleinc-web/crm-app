"""Campaign service layer."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select

from src.campaigns.models import Campaign, CampaignMember, EmailCampaignStep, EmailTemplate
from src.campaigns.schemas import (
    CampaignAnalytics,
    CampaignCreate,
    CampaignMemberCreate,
    CampaignMemberUpdate,
    CampaignUpdate,
    EmailCampaignStepCreate,
    EmailCampaignStepUpdate,
    EmailTemplateCreate,
    EmailTemplateUpdate,
    StepAnalytics,
)
from src.core.base_service import BaseService, CRUDService
from src.core.constants import DEFAULT_PAGE_SIZE
from src.core.filtering import build_token_search

logger = logging.getLogger(__name__)


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
        search: str | None = None,
        campaign_type: str | None = None,
        status: str | None = None,
        owner_id: int | None = None,
    ) -> tuple[list[Campaign], int]:
        """Get paginated list of campaigns with filters."""
        query = select(Campaign)

        if search:
            search_condition = build_token_search(search, Campaign.name)
            if search_condition is not None:
                query = query.where(search_condition)

        if campaign_type:
            query = query.where(Campaign.campaign_type == campaign_type)

        if status:
            query = query.where(Campaign.status == status)

        if owner_id:
            query = query.where(Campaign.owner_id == owner_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Campaign.created_at.desc())

        result = await self.db.execute(query)
        campaigns = list(result.scalars().all())

        return campaigns, total

    async def process_due_campaign_steps(self) -> list[dict]:
        """Process campaigns that have a due next step.

        Finds campaigns where is_executing=True and next_step_at <= now,
        sends emails for the current step, then advances or completes.
        """
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(Campaign).where(
                and_(
                    Campaign.is_executing == True,
                    Campaign.next_step_at.isnot(None),
                    Campaign.next_step_at <= now,
                )
            )
        )
        due_campaigns = list(result.scalars().all())

        processed = []
        for campaign in due_campaigns:
            try:
                step_result = await self._execute_campaign_step(campaign)
                processed.append(step_result)
            except Exception as e:
                logger.error("Failed to process step for campaign %s: %s", campaign.id, e)
                processed.append({"campaign_id": campaign.id, "status": "error", "error": str(e)})

        await self.db.flush()
        return processed

    async def _update_member_statuses(self, campaign_id: int, sent_emails) -> None:
        """Mark campaign members as 'sent' for emails that were actually queued."""
        from src.email.service import EmailService

        now = datetime.now(UTC)
        email_addresses = {e.to_email for e in sent_emails}
        email_service = EmailService(self.db)
        members_result = await self.db.execute(
            select(CampaignMember).where(CampaignMember.campaign_id == campaign_id)
        )
        for member in members_result.scalars().all():
            member_email = await email_service.get_member_email(member)
            if member_email in email_addresses:
                member.status = "sent"
                member.sent_at = now

    def _advance_to_next_step(self, campaign: Campaign, steps: list) -> None:
        """Advance campaign to the next step, or mark completed if done."""
        if campaign.current_step >= len(steps):
            campaign.status = "completed"
            campaign.is_executing = False
            campaign.next_step_at = None
        else:
            next_step = steps[campaign.current_step]
            campaign.next_step_at = datetime.now(UTC) + timedelta(days=next_step.delay_days)

    async def _execute_campaign_step(self, campaign: Campaign) -> dict:
        """Execute the current step for a campaign and schedule the next one."""
        from src.email.service import EmailService

        step_service = EmailCampaignStepService(self.db)
        steps = await step_service.get_steps(campaign.id)

        if campaign.current_step >= len(steps):
            self._advance_to_next_step(campaign, steps)
            await self._notify_campaign_completed(campaign)
            return {"campaign_id": campaign.id, "status": "completed", "reason": "all_steps_done"}

        step = steps[campaign.current_step]

        email_service = EmailService(self.db)
        sent_emails = await email_service.send_campaign_emails(
            campaign_id=campaign.id,
            template_id=step.template_id,
            sent_by_id=campaign.owner_id,
        )

        campaign.num_sent = (campaign.num_sent or 0) + len(sent_emails)
        await self._update_member_statuses(campaign.id, sent_emails)

        campaign.current_step += 1
        self._advance_to_next_step(campaign, steps)

        if campaign.status == "completed":
            await self._notify_campaign_completed(campaign)

        return {
            "campaign_id": campaign.id,
            "step_executed": campaign.current_step - 1,
            "emails_sent": len(sent_emails),
            "status": campaign.status,
        }

    async def _notify_campaign_completed(self, campaign: Campaign) -> None:
        """Send a completion notification to the campaign owner."""
        if campaign.owner_id is None:
            return
        from src.notifications.event_handler import create_completion_notification

        await create_completion_notification(
            user_id=campaign.owner_id,
            title="Campaign Completed",
            message=f"Campaign '{campaign.name}' has completed all steps",
            entity_type="campaign",
            entity_id=campaign.id,
            notification_type="campaign_completed",
        )

    async def get_campaign_stats(self, campaign_id: int) -> dict:
        # Count by status
        result = await self.db.execute(
            select(
                CampaignMember.status,
                func.count(CampaignMember.id).label("n")
            )
            .where(CampaignMember.campaign_id == campaign_id)
            .group_by(CampaignMember.status)
        )
        status_counts = {row.status: row.n for row in result.all()}

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

    async def get_campaign_analytics(self, campaign_id: int) -> CampaignAnalytics:
        """Get email analytics for a campaign, grouped by step."""
        from sqlalchemy import case

        from src.email.models import EmailQueue

        # Get campaign steps with template names
        step_result = await self.db.execute(
            select(EmailCampaignStep, EmailTemplate.name)
            .join(EmailTemplate, EmailCampaignStep.template_id == EmailTemplate.id)
            .where(EmailCampaignStep.campaign_id == campaign_id)
            .order_by(EmailCampaignStep.step_order)
        )
        step_rows = step_result.all()

        # Get email stats grouped by template_id for this campaign
        email_result = await self.db.execute(
            select(
                EmailQueue.template_id,
                func.count(EmailQueue.id).label("sent"),
                func.count(EmailQueue.opened_at).label("opened"),
                func.count(EmailQueue.clicked_at).label("clicked"),
                func.sum(
                    case((EmailQueue.status == "failed", 1), else_=0)
                ).label("failed"),
            )
            .where(EmailQueue.campaign_id == campaign_id)
            .group_by(EmailQueue.template_id)
        )
        email_stats = {row.template_id: row for row in email_result.all()}

        total_sent = 0
        total_opened = 0
        total_clicked = 0
        total_failed = 0
        steps = []

        for step, template_name in step_rows:
            stats = email_stats.get(step.template_id)
            sent = stats.sent if stats else 0
            opened = stats.opened if stats else 0
            clicked = stats.clicked if stats else 0
            failed = int(stats.failed or 0) if stats else 0

            total_sent += sent
            total_opened += opened
            total_clicked += clicked
            total_failed += failed

            steps.append(StepAnalytics(
                step_order=step.step_order,
                template_name=template_name,
                sent=sent,
                opened=opened,
                clicked=clicked,
                failed=failed,
                open_rate=round((opened / sent) * 100, 1) if sent > 0 else 0.0,
                click_rate=round((clicked / sent) * 100, 1) if sent > 0 else 0.0,
            ))

        return CampaignAnalytics(
            campaign_id=campaign_id,
            total_sent=total_sent,
            total_opened=total_opened,
            total_clicked=total_clicked,
            total_failed=total_failed,
            open_rate=round((total_opened / total_sent) * 100, 1) if total_sent > 0 else 0.0,
            click_rate=round((total_clicked / total_sent) * 100, 1) if total_sent > 0 else 0.0,
            steps=steps,
        )


class CampaignMemberService(BaseService[CampaignMember]):
    """Service for CampaignMember operations."""

    model = CampaignMember

    async def get_campaign_members(
        self,
        campaign_id: int,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[CampaignMember], int]:
        """Get members of a campaign."""
        query = select(CampaignMember).where(CampaignMember.campaign_id == campaign_id)

        if status:
            query = query.where(CampaignMember.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        members = list(result.scalars().all())

        return members, total

    async def add_member(self, data: CampaignMemberCreate) -> CampaignMember:
        member = CampaignMember(**data.model_dump())
        self.db.add(member)
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def add_members_bulk(
        self,
        campaign_id: int,
        member_type: str,
        member_ids: list[int],
    ) -> int:
        """Add multiple members to a campaign."""
        if not member_ids:
            return 0

        # Batch check: fetch all existing member_ids in one query
        result = await self.db.execute(
            select(CampaignMember.member_id).where(
                CampaignMember.campaign_id == campaign_id,
                CampaignMember.member_type == member_type,
                CampaignMember.member_id.in_(member_ids),
            )
        )
        existing_ids = set(result.scalars().all())

        # Only add members that don't already exist
        added = 0
        for member_id in member_ids:
            if member_id not in existing_ids:
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
        await self.db.delete(member)
        await self.db.flush()


class EmailTemplateService(BaseService[EmailTemplate]):
    """Service for EmailTemplate operations."""

    model = EmailTemplate

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        category: str | None = None,
    ) -> tuple[list[EmailTemplate], int]:
        """Get paginated list of email templates."""
        query = select(EmailTemplate)

        if category:
            query = query.where(EmailTemplate.category == category)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(EmailTemplate.created_at.desc())

        result = await self.db.execute(query)
        templates = list(result.scalars().all())

        return templates, total

    async def create_template(self, data: EmailTemplateCreate, user_id: int) -> EmailTemplate:
        template = EmailTemplate(**data.model_dump(), created_by_id=user_id)
        self.db.add(template)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def update_template(self, template: EmailTemplate, data: EmailTemplateUpdate) -> EmailTemplate:
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(template, field, value)
        await self.db.flush()
        await self.db.refresh(template)
        return template

    async def delete_template(self, template: EmailTemplate) -> None:
        await self.db.delete(template)
        await self.db.flush()


class EmailCampaignStepService(BaseService[EmailCampaignStep]):
    """Service for EmailCampaignStep operations."""

    model = EmailCampaignStep

    async def get_steps(self, campaign_id: int) -> list[EmailCampaignStep]:
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
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(step, field, value)
        await self.db.flush()
        await self.db.refresh(step)
        return step

    async def delete_step(self, step: EmailCampaignStep) -> None:
        await self.db.delete(step)
        await self.db.flush()

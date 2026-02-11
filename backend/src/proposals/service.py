"""Proposal service layer."""

from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from src.proposals.models import Proposal, ProposalTemplate, ProposalView
from src.proposals.schemas import ProposalCreate, ProposalUpdate
from src.core.base_service import CRUDService
from src.core.constants import DEFAULT_PAGE_SIZE

# Valid status transitions
VALID_TRANSITIONS = {
    "draft": ["sent"],
    "sent": ["viewed", "accepted", "rejected"],
    "viewed": ["accepted", "rejected"],
    "accepted": [],
    "rejected": [],
}


class ProposalService(CRUDService[Proposal, ProposalCreate, ProposalUpdate]):
    """Service for Proposal CRUD operations."""

    model = Proposal
    create_exclude_fields = set()
    update_exclude_fields = set()

    def _get_eager_load_options(self):
        return [
            selectinload(Proposal.opportunity),
            selectinload(Proposal.contact),
            selectinload(Proposal.company),
            selectinload(Proposal.quote),
            selectinload(Proposal.views),
        ]

    async def _generate_proposal_number(self) -> str:
        """Generate auto-incrementing proposal number: PR-{year}-{seq}."""
        year = datetime.now(timezone.utc).year
        prefix = f"PR-{year}-"

        result = await self.db.execute(
            select(func.count(Proposal.id)).where(
                Proposal.proposal_number.like(f"{prefix}%")
            )
        )
        count = result.scalar() or 0
        seq = count + 1
        return f"{prefix}{seq:04d}"

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        search: Optional[str] = None,
        status: Optional[str] = None,
        contact_id: Optional[int] = None,
        company_id: Optional[int] = None,
        opportunity_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        shared_entity_ids: Optional[List[int]] = None,
    ) -> Tuple[List[Proposal], int]:
        """Get paginated list of proposals with filters."""
        query = (
            select(Proposal)
            .options(
                selectinload(Proposal.opportunity),
                selectinload(Proposal.contact),
                selectinload(Proposal.company),
                selectinload(Proposal.quote),
            )
        )

        if search:
            query = query.where(
                or_(
                    Proposal.title.ilike(f"%{search}%"),
                    Proposal.proposal_number.ilike(f"%{search}%"),
                )
            )

        if status:
            query = query.where(Proposal.status == status)

        if contact_id:
            query = query.where(Proposal.contact_id == contact_id)

        if company_id:
            query = query.where(Proposal.company_id == company_id)

        if opportunity_id:
            query = query.where(Proposal.opportunity_id == opportunity_id)

        if owner_id:
            if shared_entity_ids:
                query = query.where(
                    or_(Proposal.owner_id == owner_id, Proposal.id.in_(shared_entity_ids))
                )
            else:
                query = query.where(Proposal.owner_id == owner_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Proposal.created_at.desc())

        result = await self.db.execute(query)
        proposals = list(result.scalars().all())

        return proposals, total

    async def create(self, data: ProposalCreate, user_id: int) -> Proposal:
        """Create a new proposal with auto-generated number."""
        proposal_number = await self._generate_proposal_number()

        proposal_data = data.model_dump()
        proposal_data["proposal_number"] = proposal_number
        proposal_data["created_by_id"] = user_id

        proposal = Proposal(**proposal_data)
        self.db.add(proposal)
        await self.db.flush()
        await self.db.refresh(proposal)

        return proposal

    def validate_status_transition(self, current_status: str, new_status: str) -> bool:
        """Check if a status transition is valid."""
        allowed = VALID_TRANSITIONS.get(current_status, [])
        return new_status in allowed

    async def mark_sent(self, proposal: Proposal) -> Proposal:
        """Mark a proposal as sent."""
        if not self.validate_status_transition(proposal.status, "sent"):
            raise ValueError(f"Cannot transition from '{proposal.status}' to 'sent'")
        proposal.status = "sent"
        proposal.sent_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def mark_accepted(self, proposal: Proposal) -> Proposal:
        """Mark a proposal as accepted."""
        if not self.validate_status_transition(proposal.status, "accepted"):
            raise ValueError(f"Cannot transition from '{proposal.status}' to 'accepted'")
        proposal.status = "accepted"
        proposal.accepted_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def mark_rejected(self, proposal: Proposal) -> Proposal:
        """Mark a proposal as rejected."""
        if not self.validate_status_transition(proposal.status, "rejected"):
            raise ValueError(f"Cannot transition from '{proposal.status}' to 'rejected'")
        proposal.status = "rejected"
        proposal.rejected_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def record_view(
        self, proposal_id: int, ip_address: Optional[str] = None, user_agent: Optional[str] = None
    ) -> Proposal:
        """Record a view on a proposal and increment view_count."""
        proposal = await self.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        view = ProposalView(
            proposal_id=proposal_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(view)

        now = datetime.now(timezone.utc)
        proposal.view_count = (proposal.view_count or 0) + 1
        proposal.last_viewed_at = now

        # Auto-transition from sent to viewed
        if proposal.status == "sent":
            proposal.status = "viewed"
            proposal.viewed_at = now

        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def get_public_proposal(self, proposal_number: str) -> Optional[Proposal]:
        """Get a proposal by its number for public viewing."""
        query = (
            select(Proposal)
            .options(
                selectinload(Proposal.contact),
                selectinload(Proposal.company),
            )
            .where(Proposal.proposal_number == proposal_number)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def substitute_template_variables(
        self, template_content: str, variables: dict
    ) -> str:
        """Replace {{variable}} placeholders in template content."""
        result = template_content
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value) if value else "")
        return result


class ProposalTemplateService(CRUDService[ProposalTemplate, None, None]):
    """Service for ProposalTemplate CRUD operations."""

    model = ProposalTemplate
    create_exclude_fields = set()
    update_exclude_fields = set()

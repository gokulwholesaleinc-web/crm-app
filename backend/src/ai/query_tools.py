"""Read-only CRM query tools for the AI assistant."""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.activities.models import Activity
from src.contacts.models import Contact
from src.core.filtering import build_token_search
from src.leads.models import Lead
from src.opportunities.models import Opportunity, PipelineStage

logger = logging.getLogger(__name__)


class CRMQueryTools:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search_contacts(
        self,
        search_term: str = None,
        company: str = None,
    ) -> dict[str, Any]:
        query = select(Contact).limit(10)

        if search_term:
            search_condition = build_token_search(search_term, Contact.first_name, Contact.last_name, Contact.email)
            if search_condition is not None:
                query = query.where(search_condition)

        result = await self.db.execute(query)
        contacts = result.scalars().all()

        return {
            "count": len(contacts),
            "contacts": [
                {
                    "id": c.id,
                    "name": c.full_name,
                    "email": c.email,
                    "phone": c.phone,
                    "job_title": c.job_title,
                }
                for c in contacts
            ],
        }

    async def search_leads(
        self,
        search_term: str = None,
        status: str = None,
        min_score: int = None,
    ) -> dict[str, Any]:
        query = select(Lead).limit(10)

        if search_term:
            search_condition = build_token_search(search_term, Lead.first_name, Lead.last_name, Lead.company_name)
            if search_condition is not None:
                query = query.where(search_condition)

        if status:
            query = query.where(Lead.status == status)

        if min_score:
            query = query.where(Lead.score >= min_score)

        result = await self.db.execute(query)
        leads = result.scalars().all()

        return {
            "count": len(leads),
            "leads": [
                {
                    "id": l.id,
                    "name": l.full_name,
                    "company": l.company_name,
                    "status": l.status,
                    "score": l.score,
                }
                for l in leads
            ],
        }

    async def get_pipeline_summary(self) -> dict[str, Any]:
        result = await self.db.execute(
            select(
                PipelineStage.name,
                func.count(Opportunity.id).label("count"),
                func.sum(Opportunity.amount).label("total"),
            )
            .outerjoin(Opportunity)
            .where(PipelineStage.is_active == True)
            .group_by(PipelineStage.id)
            .order_by(PipelineStage.order)
        )

        stages = []
        total_value = 0
        total_deals = 0

        for row in result.all():
            amount = float(row.total or 0)
            stages.append({
                "stage": row.name,
                "deals": row.count or 0,
                "value": amount,
            })
            total_value += amount
            total_deals += row.count or 0

        return {
            "total_deals": total_deals,
            "total_value": total_value,
            "by_stage": stages,
        }

    async def get_upcoming_tasks(self, user_id: int, days: int = 7) -> dict[str, Any]:
        future = datetime.now() + timedelta(days=days)

        result = await self.db.execute(
            select(Activity)
            .where(
                or_(
                    Activity.owner_id == user_id,
                    Activity.assigned_to_id == user_id,
                )
            )
            .where(Activity.is_completed == False)
            .where(Activity.due_date <= future.date())
            .order_by(Activity.due_date.asc())
            .limit(10)
        )

        tasks = result.scalars().all()

        return {
            "count": len(tasks),
            "tasks": [
                {
                    "id": t.id,
                    "subject": t.subject,
                    "type": t.activity_type,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "priority": t.priority,
                }
                for t in tasks
            ],
        }

    async def get_recent_activities(
        self,
        entity_type: str = None,
        entity_id: int = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        query = select(Activity).order_by(Activity.created_at.desc()).limit(limit)

        if entity_type and entity_id:
            query = query.where(
                Activity.entity_type == entity_type,
                Activity.entity_id == entity_id,
            )

        result = await self.db.execute(query)
        activities = result.scalars().all()

        return {
            "count": len(activities),
            "activities": [
                {
                    "id": a.id,
                    "type": a.activity_type,
                    "subject": a.subject,
                    "created_at": a.created_at.isoformat(),
                }
                for a in activities
            ],
        }

    async def get_kpis(self) -> dict[str, Any]:
        contacts = await self.db.execute(select(func.count(Contact.id)))
        contacts_count = contacts.scalar() or 0

        leads = await self.db.execute(
            select(func.count(Lead.id)).where(
                Lead.status.in_(["new", "contacted", "qualified"])
            )
        )
        leads_count = leads.scalar() or 0

        pipeline = await self.db.execute(
            select(func.sum(Opportunity.amount))
            .join(PipelineStage)
            .where(PipelineStage.is_won == False, PipelineStage.is_lost == False)
        )
        pipeline_value = float(pipeline.scalar() or 0)

        return {
            "total_contacts": contacts_count,
            "open_leads": leads_count,
            "pipeline_value": pipeline_value,
        }

    async def search_quotes(self, args: dict[str, Any]) -> dict[str, Any]:
        from src.quotes.models import Quote

        query = select(Quote).order_by(Quote.created_at.desc()).limit(args.get("limit", 10))

        if args.get("status"):
            query = query.where(Quote.status == args["status"])

        if args.get("search_term"):
            search_condition = build_token_search(args["search_term"], Quote.title)
            if search_condition is not None:
                query = query.where(search_condition)

        result = await self.db.execute(query)
        quotes = result.scalars().all()

        return {
            "count": len(quotes),
            "quotes": [
                {
                    "id": q.id,
                    "title": q.title,
                    "quote_number": q.quote_number,
                    "status": q.status,
                    "total": float(q.total) if q.total else 0,
                    "valid_until": q.valid_until.isoformat() if q.valid_until else None,
                }
                for q in quotes
            ],
        }

    async def get_quote_details(self, args: dict[str, Any]) -> dict[str, Any]:
        from src.quotes.models import Quote

        result = await self.db.execute(
            select(Quote).where(Quote.id == args["quote_id"])
        )
        quote = result.scalar_one_or_none()
        if not quote:
            return {"error": f"Quote with ID {args['quote_id']} not found."}

        return {
            "id": quote.id,
            "title": quote.title,
            "quote_number": quote.quote_number,
            "status": quote.status,
            "subtotal": float(quote.subtotal) if quote.subtotal else 0,
            "tax_amount": float(quote.tax_amount) if quote.tax_amount else 0,
            "total": float(quote.total) if quote.total else 0,
            "valid_until": quote.valid_until.isoformat() if quote.valid_until else None,
            "payment_type": getattr(quote, "payment_type", None),
            "line_items": [
                {
                    "description": li.description,
                    "quantity": li.quantity,
                    "unit_price": float(li.unit_price) if li.unit_price else 0,
                    "total": float(li.total) if li.total else 0,
                }
                for li in (quote.line_items or [])
            ],
        }

    async def search_proposals(self, args: dict[str, Any]) -> dict[str, Any]:
        from src.proposals.models import Proposal

        query = select(Proposal).order_by(Proposal.created_at.desc()).limit(args.get("limit", 10))

        if args.get("status"):
            query = query.where(Proposal.status == args["status"])

        if args.get("search_term"):
            search_condition = build_token_search(args["search_term"], Proposal.title)
            if search_condition is not None:
                query = query.where(search_condition)

        result = await self.db.execute(query)
        proposals = result.scalars().all()

        return {
            "count": len(proposals),
            "proposals": [
                {
                    "id": p.id,
                    "title": p.title,
                    "status": p.status,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in proposals
            ],
        }

    async def get_payment_summary(self) -> dict[str, Any]:
        from src.payments.models import Payment

        result = await self.db.execute(
            select(
                Payment.status,
                func.count(Payment.id).label("count"),
                func.sum(Payment.amount).label("total"),
            ).group_by(Payment.status)
        )

        by_status = {}
        grand_total = 0
        total_count = 0
        for row in result.all():
            amount = float(row.total or 0)
            by_status[row.status] = {
                "count": row.count or 0,
                "total": amount,
            }
            grand_total += amount
            total_count += row.count or 0

        return {
            "total_payments": total_count,
            "total_amount": grand_total,
            "by_status": by_status,
        }

    async def list_recent_payments(self, args: dict[str, Any]) -> dict[str, Any]:
        from src.payments.models import Payment

        query = select(Payment).order_by(Payment.created_at.desc()).limit(args.get("limit", 10))

        if args.get("status"):
            query = query.where(Payment.status == args["status"])

        result = await self.db.execute(query)
        payments = result.scalars().all()

        return {
            "count": len(payments),
            "payments": [
                {
                    "id": p.id,
                    "amount": float(p.amount) if p.amount else 0,
                    "status": p.status,
                    "payment_date": p.payment_date.isoformat() if p.payment_date else None,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in payments
            ],
        }

    async def get_campaign_stats(self, args: dict[str, Any]) -> dict[str, Any]:
        from src.campaigns.models import Campaign

        if args.get("campaign_id"):
            result = await self.db.execute(
                select(Campaign).where(Campaign.id == args["campaign_id"])
            )
            campaign = result.scalar_one_or_none()
            if not campaign:
                return {"error": f"Campaign with ID {args['campaign_id']} not found."}

            return {
                "id": campaign.id,
                "name": campaign.name,
                "status": campaign.status,
                "type": getattr(campaign, "campaign_type", None),
                "start_date": campaign.start_date.isoformat() if campaign.start_date else None,
                "end_date": campaign.end_date.isoformat() if campaign.end_date else None,
            }

        result = await self.db.execute(
            select(
                Campaign.status,
                func.count(Campaign.id).label("count"),
            ).group_by(Campaign.status)
        )

        by_status = {}
        total = 0
        for row in result.all():
            by_status[row.status] = row.count or 0
            total += row.count or 0

        return {"total_campaigns": total, "by_status": by_status}

    async def get_deal_coaching(self, args: dict[str, Any]) -> dict[str, Any]:
        from datetime import date

        result = await self.db.execute(
            select(Opportunity).where(Opportunity.id == args["opportunity_id"])
        )
        opp = result.scalar_one_or_none()
        if not opp:
            return {"error": f"Opportunity with ID {args['opportunity_id']} not found."}

        tips = []

        activity_result = await self.db.execute(
            select(func.count(Activity.id))
            .where(Activity.entity_type == "opportunities")
            .where(Activity.entity_id == opp.id)
        )
        activity_count = activity_result.scalar() or 0

        if activity_count == 0:
            tips.append("No activities recorded. Schedule an initial meeting or call.")
        elif activity_count < 3:
            tips.append("Low activity. Increase engagement with more touchpoints.")

        if opp.expected_close_date:
            days_to_close = (opp.expected_close_date - date.today()).days
            if days_to_close < 0:
                tips.append(f"Deal is {abs(days_to_close)} days overdue. Re-evaluate or update the close date.")
            elif days_to_close <= 7:
                tips.append(f"Closing in {days_to_close} days. Push for a decision.")
            elif days_to_close <= 30:
                tips.append("Closing within a month. Ensure all stakeholders are aligned.")

        if not opp.contact_id:
            tips.append("No contact assigned. Associate a decision maker.")

        if not tips:
            tips.append("Deal looks healthy. Continue current engagement strategy.")

        return {
            "opportunity_id": opp.id,
            "name": opp.name,
            "amount": float(opp.amount) if opp.amount else 0,
            "coaching_tips": tips,
        }

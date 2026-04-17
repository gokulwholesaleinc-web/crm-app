"""CRM analytics tools: pipeline reports, forecasts, and pipeline intelligence."""

import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.activities.models import Activity
from src.opportunities.models import Opportunity, PipelineStage

logger = logging.getLogger(__name__)


class CRMAnalyticsTools:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_pipeline_report(self, args: dict[str, Any]) -> dict[str, Any]:
        date_from = None
        date_to = None

        if args.get("date_from"):
            try:
                date_from = date.fromisoformat(args["date_from"])
            except ValueError:
                pass
        if args.get("date_to"):
            try:
                date_to = date.fromisoformat(args["date_to"])
            except ValueError:
                pass

        query = (
            select(
                PipelineStage.name,
                PipelineStage.probability,
                func.count(Opportunity.id).label("count"),
                func.sum(Opportunity.amount).label("total"),
                func.avg(Opportunity.amount).label("avg_amount"),
            )
            .outerjoin(Opportunity)
            .where(PipelineStage.is_active == True)
        )

        if date_from:
            query = query.where(Opportunity.created_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            query = query.where(Opportunity.created_at <= datetime.combine(date_to, datetime.max.time()))

        query = query.group_by(PipelineStage.id).order_by(PipelineStage.order)
        result = await self.db.execute(query)

        stages = []
        total_value = 0
        total_weighted = 0
        total_deals = 0

        for row in result.all():
            amount = float(row.total or 0)
            avg = float(row.avg_amount or 0)
            weighted = amount * (row.probability / 100)
            stages.append({
                "stage": row.name,
                "deals": row.count or 0,
                "total_value": amount,
                "avg_deal_size": round(avg, 2),
                "probability": row.probability,
                "weighted_value": round(weighted, 2),
            })
            total_value += amount
            total_weighted += weighted
            total_deals += row.count or 0

        return {
            "report_type": "pipeline",
            "date_from": args.get("date_from"),
            "date_to": args.get("date_to"),
            "total_deals": total_deals,
            "total_value": total_value,
            "total_weighted_value": round(total_weighted, 2),
            "by_stage": stages,
        }

    async def generate_activity_report(self, args: dict[str, Any], user_id: int) -> dict[str, Any]:
        report_user_id = args.get("user_id", user_id)
        date_from = None
        date_to = None

        if args.get("date_from"):
            try:
                date_from = date.fromisoformat(args["date_from"])
            except ValueError:
                pass
        if args.get("date_to"):
            try:
                date_to = date.fromisoformat(args["date_to"])
            except ValueError:
                pass

        query = select(Activity).where(
            or_(
                Activity.owner_id == report_user_id,
                Activity.assigned_to_id == report_user_id,
            )
        )

        if date_from:
            query = query.where(Activity.created_at >= datetime.combine(date_from, datetime.min.time()))
        if date_to:
            query = query.where(Activity.created_at <= datetime.combine(date_to, datetime.max.time()))

        result = await self.db.execute(query)
        activities = result.scalars().all()

        by_type = {}
        completed = 0
        pending = 0
        for a in activities:
            by_type[a.activity_type] = by_type.get(a.activity_type, 0) + 1
            if a.is_completed:
                completed += 1
            else:
                pending += 1

        return {
            "report_type": "activity",
            "user_id": report_user_id,
            "date_from": args.get("date_from"),
            "date_to": args.get("date_to"),
            "total_activities": len(activities),
            "completed": completed,
            "pending": pending,
            "by_type": by_type,
        }

    async def analyze_pipeline(self, args: dict[str, Any]) -> dict[str, Any]:
        days = args.get("days", 30)
        now = datetime.now()
        period_start = now - timedelta(days=days)
        prev_period_start = period_start - timedelta(days=days)

        result = await self.db.execute(
            select(
                PipelineStage.name,
                PipelineStage.probability,
                PipelineStage.is_won,
                PipelineStage.is_lost,
                func.count(Opportunity.id).label("count"),
                func.sum(Opportunity.amount).label("total"),
                func.avg(Opportunity.amount).label("avg_amount"),
            )
            .outerjoin(Opportunity)
            .where(PipelineStage.is_active == True)
            .group_by(PipelineStage.id)
            .order_by(PipelineStage.order)
        )

        stages = []
        total_value = 0
        total_deals = 0
        weighted_value = 0
        won_count = 0
        lost_count = 0
        open_count = 0

        for row in result.all():
            amount = float(row.total or 0)
            avg = float(row.avg_amount or 0)
            w_value = amount * (row.probability / 100)
            count = row.count or 0

            stages.append({
                "stage": row.name,
                "deals": count,
                "total_value": amount,
                "avg_deal_size": round(avg, 2),
                "probability": row.probability,
                "weighted_value": round(w_value, 2),
            })
            total_value += amount
            total_deals += count
            weighted_value += w_value

            if row.is_won:
                won_count += count
            elif row.is_lost:
                lost_count += count
            else:
                open_count += count

        closed = won_count + lost_count
        win_rate = round((won_count / closed * 100), 1) if closed > 0 else None

        stale_cutoff = now - timedelta(days=7)
        stale_result = await self.db.execute(
            select(func.count(Opportunity.id))
            .join(PipelineStage)
            .where(
                PipelineStage.is_won == False,
                PipelineStage.is_lost == False,
            )
            .where(
                ~Opportunity.id.in_(
                    select(Activity.entity_id)
                    .where(Activity.entity_type == "opportunities")
                    .where(Activity.created_at > stale_cutoff)
                )
            )
        )
        deals_at_risk = stale_result.scalar() or 0

        upcoming_cutoff = (now + timedelta(days=14)).date()
        upcoming_result = await self.db.execute(
            select(func.count(Opportunity.id))
            .join(PipelineStage)
            .where(
                PipelineStage.is_won == False,
                PipelineStage.is_lost == False,
                Opportunity.expected_close_date <= upcoming_cutoff,
                Opportunity.expected_close_date >= now.date(),
            )
        )
        upcoming_closes = upcoming_result.scalar() or 0

        prev_result = await self.db.execute(
            select(
                func.count(Opportunity.id).label("count"),
                func.sum(Opportunity.amount).label("total"),
            )
            .join(PipelineStage)
            .where(
                Opportunity.created_at >= datetime.combine(prev_period_start.date(), datetime.min.time()),
                Opportunity.created_at < datetime.combine(period_start.date(), datetime.min.time()),
                PipelineStage.is_won == True,
            )
        )
        prev_row = prev_result.one_or_none()
        prev_won_value = float(prev_row.total or 0) if prev_row else 0

        cur_result = await self.db.execute(
            select(func.sum(Opportunity.amount))
            .join(PipelineStage)
            .where(
                Opportunity.created_at >= datetime.combine(period_start.date(), datetime.min.time()),
                PipelineStage.is_won == True,
            )
        )
        cur_won_value = float(cur_result.scalar() or 0)

        recommendations = []
        if deals_at_risk > 0:
            recommendations.append(f"{deals_at_risk} deal(s) have no recent activity - follow up immediately.")
        if upcoming_closes > 0:
            recommendations.append(f"{upcoming_closes} deal(s) closing in the next 14 days - push for decisions.")
        if win_rate is not None and win_rate < 30:
            recommendations.append("Win rate is below 30% - review qualification criteria.")
        if open_count > 0 and total_value > 0:
            avg_deal = total_value / open_count
            recommendations.append(f"Average open deal size: ${avg_deal:,.0f}.")

        return {
            "analysis_period_days": days,
            "total_deals": total_deals,
            "open_deals": open_count,
            "won_deals": won_count,
            "lost_deals": lost_count,
            "total_pipeline_value": total_value,
            "weighted_forecast": round(weighted_value, 2),
            "win_rate_percent": win_rate,
            "avg_deal_size": round(total_value / total_deals, 2) if total_deals > 0 else 0,
            "deals_at_risk": deals_at_risk,
            "upcoming_closes_14d": upcoming_closes,
            "current_period_won_value": cur_won_value,
            "previous_period_won_value": prev_won_value,
            "by_stage": stages,
            "recommendations": recommendations,
        }

    async def suggest_improvements(self, args: dict[str, Any]) -> dict[str, Any]:
        opportunity_id = args.get("opportunity_id")

        if opportunity_id:
            result = await self.db.execute(
                select(Opportunity).where(Opportunity.id == opportunity_id)
            )
            opp = result.scalar_one_or_none()
            if not opp:
                return {"error": f"Opportunity with ID {opportunity_id} not found."}

            act_result = await self.db.execute(
                select(func.count(Activity.id))
                .where(Activity.entity_type == "opportunities", Activity.entity_id == opp.id)
            )
            activity_count = act_result.scalar() or 0

            week_ago = datetime.now() - timedelta(days=7)
            recent_result = await self.db.execute(
                select(func.count(Activity.id))
                .where(
                    Activity.entity_type == "opportunities",
                    Activity.entity_id == opp.id,
                    Activity.created_at > week_ago,
                )
            )
            recent_count = recent_result.scalar() or 0

            suggestions = []
            risk_factors = []

            if activity_count == 0:
                risk_factors.append("No activities recorded at all.")
                suggestions.append("Schedule an initial call or meeting immediately.")
            elif recent_count == 0:
                risk_factors.append("No activity in the past week.")
                suggestions.append("Re-engage with a follow-up call or email.")

            if not opp.contact_id:
                risk_factors.append("No contact assigned to this deal.")
                suggestions.append("Associate a decision-maker contact.")

            if opp.expected_close_date:
                days_to_close = (opp.expected_close_date - date.today()).days
                if days_to_close < 0:
                    risk_factors.append(f"Deal is {abs(days_to_close)} days overdue.")
                    suggestions.append("Update the close date or re-qualify the opportunity.")
                elif days_to_close <= 7:
                    suggestions.append("Closing soon - send a proposal or finalize terms.")

            if float(opp.amount or 0) > 0 and activity_count < 3:
                suggestions.append("Increase engagement - schedule more touchpoints for this deal value.")

            if not risk_factors:
                risk_factors.append("No major risks identified.")
            if not suggestions:
                suggestions.append("Deal looks healthy. Maintain current engagement strategy.")

            return {
                "opportunity_id": opp.id,
                "name": opp.name,
                "amount": float(opp.amount) if opp.amount else 0,
                "activity_count": activity_count,
                "recent_activity_count": recent_count,
                "risk_factors": risk_factors,
                "suggested_actions": suggestions,
            }

        pipeline_analysis = await self.analyze_pipeline({"days": 30})

        suggestions = []

        stages = pipeline_analysis.get("by_stage", [])
        for stage in stages:
            if stage["deals"] > 5 and stage.get("probability", 0) < 50:
                suggestions.append(
                    f"Stage '{stage['stage']}' has {stage['deals']} deals but low probability - "
                    f"review qualification criteria for this stage."
                )

        if pipeline_analysis.get("deals_at_risk", 0) > 0:
            suggestions.append(
                f"Follow up on {pipeline_analysis['deals_at_risk']} stale deal(s) immediately."
            )

        if pipeline_analysis.get("win_rate_percent") and pipeline_analysis["win_rate_percent"] < 25:
            suggestions.append(
                "Win rate is low. Consider tightening lead qualification criteria."
            )

        if pipeline_analysis.get("upcoming_closes_14d", 0) > 0:
            suggestions.append(
                f"Prioritize {pipeline_analysis['upcoming_closes_14d']} deals closing within 14 days."
            )

        if not suggestions:
            suggestions.append("Pipeline looks healthy. Continue current strategies.")

        return {
            "pipeline_summary": {
                "total_value": pipeline_analysis["total_pipeline_value"],
                "open_deals": pipeline_analysis["open_deals"],
                "win_rate": pipeline_analysis["win_rate_percent"],
                "weighted_forecast": pipeline_analysis["weighted_forecast"],
            },
            "improvement_suggestions": suggestions,
        }

    async def get_stale_deals(self, args: dict[str, Any]) -> dict[str, Any]:
        days_idle = args.get("days_idle", 7)
        cutoff = datetime.now() - timedelta(days=days_idle)

        active_opp_ids = (
            select(Activity.entity_id)
            .where(Activity.entity_type == "opportunities")
            .where(Activity.created_at > cutoff)
        )

        result = await self.db.execute(
            select(Opportunity)
            .join(PipelineStage)
            .where(
                PipelineStage.is_won == False,
                PipelineStage.is_lost == False,
                ~Opportunity.id.in_(active_opp_ids),
            )
            .order_by(Opportunity.amount.desc().nullslast())
            .limit(20)
        )
        stale_opps = result.scalars().all()

        deals = []
        for opp in stale_opps:
            last_act = await self.db.execute(
                select(Activity.created_at)
                .where(Activity.entity_type == "opportunities", Activity.entity_id == opp.id)
                .order_by(Activity.created_at.desc())
                .limit(1)
            )
            last_activity_row = last_act.scalar_one_or_none()
            last_activity_date = last_activity_row.isoformat() if last_activity_row else None

            suggestion = "Schedule a follow-up call."
            if float(opp.amount or 0) > 10000:
                suggestion = "High-value deal - prioritize a meeting or proposal."
            if opp.expected_close_date and opp.expected_close_date < date.today():
                suggestion = "Deal is overdue - re-qualify or close it."

            deals.append({
                "id": opp.id,
                "name": opp.name,
                "amount": float(opp.amount) if opp.amount else 0,
                "expected_close_date": opp.expected_close_date.isoformat() if opp.expected_close_date else None,
                "last_activity_date": last_activity_date,
                "suggested_action": suggestion,
            })

        return {
            "days_idle_threshold": days_idle,
            "stale_deals_count": len(deals),
            "deals": deals,
        }

    async def get_follow_up_priorities(self, user_id: int) -> dict[str, Any]:
        priorities = []

        result = await self.db.execute(
            select(Opportunity)
            .join(PipelineStage)
            .where(
                Opportunity.owner_id == user_id,
                PipelineStage.is_won == False,
                PipelineStage.is_lost == False,
            )
            .order_by(Opportunity.expected_close_date.asc().nullslast())
            .limit(20)
        )
        opportunities = result.scalars().all()

        for opp in opportunities:
            last_act = await self.db.execute(
                select(Activity.created_at)
                .where(Activity.entity_type == "opportunities", Activity.entity_id == opp.id)
                .order_by(Activity.created_at.desc())
                .limit(1)
            )
            last_act_date = last_act.scalar_one_or_none()

            days_since_contact = None
            if last_act_date:
                days_since_contact = (datetime.now(last_act_date.tzinfo) - last_act_date).days if last_act_date.tzinfo else (datetime.now() - last_act_date).days

            urgency = 0
            reasons = []

            if days_since_contact is None:
                urgency += 50
                reasons.append("Never contacted")
            elif days_since_contact > 14:
                urgency += 40
                reasons.append(f"No contact in {days_since_contact} days")
            elif days_since_contact > 7:
                urgency += 20
                reasons.append(f"Last contact {days_since_contact} days ago")

            if opp.expected_close_date:
                days_to_close = (opp.expected_close_date - date.today()).days
                if days_to_close < 0:
                    urgency += 30
                    reasons.append("Past expected close date")
                elif days_to_close <= 7:
                    urgency += 25
                    reasons.append(f"Closing in {days_to_close} days")
                elif days_to_close <= 14:
                    urgency += 15
                    reasons.append(f"Closing in {days_to_close} days")

            amount = float(opp.amount or 0)
            if amount > 50000:
                urgency += 15
                reasons.append("High-value deal")
            elif amount > 10000:
                urgency += 10

            suggestion = "Send a follow-up email."
            if urgency > 60:
                suggestion = "Urgent: schedule a call or meeting immediately."
            elif urgency > 30:
                suggestion = "Schedule a follow-up call this week."

            priorities.append({
                "opportunity_id": opp.id,
                "opportunity_name": opp.name,
                "amount": amount,
                "contact_id": opp.contact_id,
                "days_since_last_contact": days_since_contact,
                "expected_close_date": opp.expected_close_date.isoformat() if opp.expected_close_date else None,
                "urgency_score": urgency,
                "reasons": reasons,
                "suggested_action": suggestion,
            })

        priorities.sort(key=lambda x: x["urgency_score"], reverse=True)

        return {
            "count": len(priorities),
            "priorities": priorities,
        }

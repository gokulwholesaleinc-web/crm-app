"""Write/action CRM tools for the AI assistant."""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.activities.models import Activity
from src.activities.schemas import ActivityCreate
from src.activities.service import ActivityService
from src.contacts.models import Contact
from src.leads.schemas import LeadCreate, LeadUpdate
from src.leads.service import LeadService
from src.notes.schemas import NoteCreate
from src.notes.service import NoteService
from src.opportunities.models import Opportunity, PipelineStage
from src.opportunities.schemas import OpportunityUpdate
from src.opportunities.service import OpportunityService
from src.ai.learning_service import AILearningService

logger = logging.getLogger(__name__)


class CRMActionTools:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_lead(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        service = LeadService(self.db)
        lead_data = LeadCreate(
            first_name=args["first_name"],
            last_name=args["last_name"],
            email=args.get("email"),
            company_name=args.get("company_name"),
            source_details=args.get("source"),
            description=args.get("notes"),
        )
        lead = await service.create(lead_data, user_id)
        return {
            "success": True,
            "lead_id": lead.id,
            "name": lead.full_name,
            "status": lead.status,
            "score": lead.score,
            "message": f"Lead '{lead.full_name}' created successfully.",
        }

    async def update_lead_status(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        service = LeadService(self.db)
        lead = await service.get_by_id(args["lead_id"])
        if not lead:
            return {"error": f"Lead with ID {args['lead_id']} not found."}

        old_status = lead.status
        update_data = LeadUpdate(status=args["new_status"])
        if args.get("reason"):
            update_data.description = f"{lead.description or ''}\n\nStatus change ({old_status} -> {args['new_status']}): {args['reason']}".strip()

        lead = await service.update(lead, update_data, user_id)
        return {
            "success": True,
            "lead_id": lead.id,
            "name": lead.full_name,
            "old_status": old_status,
            "new_status": lead.status,
            "message": f"Lead '{lead.full_name}' status changed from '{old_status}' to '{lead.status}'.",
        }

    async def create_activity(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        service = ActivityService(self.db)

        due = None
        if args.get("due_date"):
            try:
                due = date.fromisoformat(args["due_date"])
            except ValueError:
                return {"error": f"Invalid date format: {args['due_date']}. Use YYYY-MM-DD."}

        activity_data = ActivityCreate(
            subject=args["subject"],
            activity_type=args["activity_type"],
            entity_type=args["entity_type"],
            entity_id=args["entity_id"],
            due_date=due,
            priority=args.get("priority", "normal"),
            description=args.get("notes"),
        )
        activity = await service.create(activity_data, user_id)
        return {
            "success": True,
            "activity_id": activity.id,
            "subject": activity.subject,
            "type": activity.activity_type,
            "due_date": activity.due_date.isoformat() if activity.due_date else None,
            "message": f"Activity '{activity.subject}' created successfully.",
        }

    async def update_opportunity_stage(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        service = OpportunityService(self.db)
        opportunity = await service.get_by_id(args["opportunity_id"])
        if not opportunity:
            return {"error": f"Opportunity with ID {args['opportunity_id']} not found."}

        stage_result = await self.db.execute(
            select(PipelineStage).where(PipelineStage.id == args["stage_id"])
        )
        stage = stage_result.scalar_one_or_none()
        if not stage:
            return {"error": f"Pipeline stage with ID {args['stage_id']} not found."}

        old_stage_name = "Unknown"
        if opportunity.pipeline_stage:
            old_stage_name = opportunity.pipeline_stage.name

        update_data = OpportunityUpdate(pipeline_stage_id=args["stage_id"])
        if args.get("notes"):
            desc = opportunity.description or ""
            update_data.description = f"{desc}\n\nStage change: {args['notes']}".strip()

        opportunity = await service.update(opportunity, update_data, user_id)
        return {
            "success": True,
            "opportunity_id": opportunity.id,
            "name": opportunity.name,
            "old_stage": old_stage_name,
            "new_stage": stage.name,
            "message": f"Opportunity '{opportunity.name}' moved from '{old_stage_name}' to '{stage.name}'.",
        }

    async def add_note(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        service = NoteService(self.db)
        note_data = NoteCreate(
            entity_type=args["entity_type"],
            entity_id=args["entity_id"],
            content=args["content"],
        )
        note = await service.create(note_data, user_id)
        return {
            "success": True,
            "note_id": note["id"],
            "entity_type": args["entity_type"],
            "entity_id": args["entity_id"],
            "message": f"Note added to {args['entity_type']} #{args['entity_id']}.",
        }

    async def remember_preference(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        learning_service = AILearningService(self.db)
        learning = await learning_service.learn_preference(
            user_id=user_id,
            category=args["category"],
            key=args["key"],
            value=args["value"],
        )
        return {
            "success": True,
            "message": f"Remembered: {args['key']} = {args['value']}",
            "learning_id": learning.id,
        }

    async def create_and_send_quote(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        from src.quotes.service import QuoteService
        from src.quotes.schemas import QuoteCreate, QuoteLineItemCreate
        import os

        valid_days = args.get("valid_days", 30)
        valid_until = (date.today() + timedelta(days=valid_days))

        line_items = []
        for item in (args.get("line_items") or []):
            line_items.append(QuoteLineItemCreate(
                description=item.get("description", "Item"),
                quantity=item.get("quantity", 1),
                unit_price=item.get("unit_price", 0),
            ))

        quote_data = QuoteCreate(
            title=args["title"],
            contact_id=args["contact_id"],
            opportunity_id=args.get("opportunity_id"),
            valid_until=valid_until,
            line_items=line_items if line_items else None,
            owner_id=user_id,
        )

        service = QuoteService(self.db)
        quote = await service.create(quote_data, user_id)

        base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        public_url = f"{base_url}/quotes/public/{quote.quote_number}"

        result = {
            "success": True,
            "quote_id": quote.id,
            "quote_number": quote.quote_number,
            "total": float(quote.total) if quote.total else 0,
            "status": quote.status,
            "valid_until": valid_until.isoformat(),
            "public_url": public_url,
            "message": f"Quote '{quote.quote_number}' created successfully.",
        }

        if args.get("send_immediately"):
            send_result = await self._send_quote_email(quote, user_id)
            result["email_sent"] = send_result.get("success", False)
            result["status"] = "sent" if send_result.get("success") else result["status"]
            result["message"] += f" Email {'sent with public link' if send_result.get('success') else 'failed'}."

        return result

    async def _send_quote_email(self, quote, user_id: int) -> Dict[str, Any]:
        import os

        if not quote.contact_id:
            return {"success": False, "error": "No contact associated with quote."}

        contact_result = await self.db.execute(
            select(Contact).where(Contact.id == quote.contact_id)
        )
        contact = contact_result.scalar_one_or_none()
        if not contact or not contact.email:
            return {"success": False, "error": "Contact has no email address."}

        from src.email.branded_templates import TenantBrandingHelper, render_quote_email
        from src.email.service import EmailService

        branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)

        base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        view_url = f"{base_url}/quotes/public/{quote.quote_number}"

        quote_data = {
            "quote_number": quote.quote_number,
            "client_name": contact.full_name,
            "total": str(float(quote.total) if quote.total else "0.00"),
            "currency": quote.currency or "USD",
            "valid_until": quote.valid_until.isoformat() if quote.valid_until else "",
            "items": [
                {
                    "description": li.description,
                    "quantity": str(li.quantity),
                    "unit_price": str(float(li.unit_price) if li.unit_price else "0"),
                    "total": str(float(li.total) if li.total else "0"),
                }
                for li in (quote.line_items or [])
            ],
            "view_url": view_url,
        }
        subject, html_body = render_quote_email(branding, quote_data)

        email_service = EmailService(self.db)
        await email_service.queue_email(
            to_email=contact.email,
            subject=subject,
            body=html_body,
            sent_by_id=user_id,
            entity_type="quotes",
            entity_id=quote.id,
        )

        if quote.status == "draft":
            quote.status = "sent"
            quote.sent_at = datetime.now(timezone.utc)
            await self.db.flush()

        return {"success": True}

    async def resend_quote(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        from src.quotes.models import Quote
        from sqlalchemy.orm import selectinload

        result = await self.db.execute(
            select(Quote)
            .options(selectinload(Quote.line_items))
            .where(Quote.id == args["quote_id"])
        )
        quote = result.scalar_one_or_none()
        if not quote:
            return {"error": f"Quote with ID {args['quote_id']} not found."}

        send_result = await self._send_quote_email(quote, user_id)
        if send_result.get("success"):
            return {"success": True, "message": f"Quote '{quote.quote_number}' resent successfully."}
        return {"success": False, "error": send_result.get("error", "Failed to send email.")}

    async def create_and_send_proposal(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        from src.proposals.service import ProposalService
        from src.proposals.schemas import ProposalCreate

        opp_result = await self.db.execute(
            select(Opportunity).where(Opportunity.id == args["opportunity_id"])
        )
        opp = opp_result.scalar_one_or_none()
        if not opp:
            return {"error": f"Opportunity with ID {args['opportunity_id']} not found."}

        proposal_data = ProposalCreate(
            title=f"Proposal for {opp.name}",
            opportunity_id=opp.id,
            contact_id=opp.contact_id,
            company_id=opp.company_id,
            executive_summary=f"We are pleased to present this proposal for {opp.name}.",
            pricing_section=f"Proposed investment: {opp.currency or 'USD'} {float(opp.amount or 0):,.2f}",
            owner_id=user_id,
        )

        service = ProposalService(self.db)
        proposal = await service.create(proposal_data, user_id)

        result = {
            "success": True,
            "proposal_id": proposal.id,
            "proposal_number": proposal.proposal_number,
            "title": proposal.title,
            "status": proposal.status,
            "message": f"Proposal '{proposal.proposal_number}' created successfully.",
        }

        if args.get("send_immediately") and opp.contact_id:
            send_result = await self._send_proposal_email(proposal, opp, user_id)
            result["email_sent"] = send_result.get("success", False)
            result["message"] += f" Email {'sent' if send_result.get('success') else 'failed'}."

        return result

    async def _send_proposal_email(self, proposal, opportunity, user_id: int) -> Dict[str, Any]:
        if not opportunity.contact_id:
            return {"success": False, "error": "No contact on opportunity."}

        contact_result = await self.db.execute(
            select(Contact).where(Contact.id == opportunity.contact_id)
        )
        contact = contact_result.scalar_one_or_none()
        if not contact or not contact.email:
            return {"success": False, "error": "Contact has no email address."}

        from src.email.branded_templates import TenantBrandingHelper, render_proposal_email
        from src.email.service import EmailService

        branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)
        proposal_data = {
            "proposal_title": proposal.title,
            "client_name": contact.full_name,
            "summary": proposal.executive_summary or "",
            "total": str(float(opportunity.amount or 0)),
            "currency": opportunity.currency or "USD",
        }
        subject, html_body = render_proposal_email(branding, proposal_data)

        email_service = EmailService(self.db)
        await email_service.queue_email(
            to_email=contact.email,
            subject=subject,
            body=html_body,
            sent_by_id=user_id,
            entity_type="proposals",
            entity_id=proposal.id,
        )
        return {"success": True}

    async def resend_proposal(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        from src.proposals.models import Proposal

        result = await self.db.execute(
            select(Proposal).where(Proposal.id == args["proposal_id"])
        )
        proposal = result.scalar_one_or_none()
        if not proposal:
            return {"error": f"Proposal with ID {args['proposal_id']} not found."}

        if not proposal.opportunity_id:
            return {"error": "Proposal has no associated opportunity."}

        opp_result = await self.db.execute(
            select(Opportunity).where(Opportunity.id == proposal.opportunity_id)
        )
        opp = opp_result.scalar_one_or_none()
        if not opp:
            return {"error": "Associated opportunity not found."}

        send_result = await self._send_proposal_email(proposal, opp, user_id)
        if send_result.get("success"):
            return {"success": True, "message": f"Proposal '{proposal.proposal_number}' resent successfully."}
        return {"success": False, "error": send_result.get("error", "Failed to send email.")}

    async def create_payment_link(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        from src.payments.service import PaymentService

        amount = args["amount"]
        currency = args.get("currency", "USD")
        contact_id = args.get("contact_id")
        quote_id = args.get("quote_id")
        description = args.get("description", f"Payment of {currency} {amount}")

        payment_service = PaymentService(self.db)

        customer_id = None
        if contact_id:
            customer = await payment_service.sync_customer(contact_id=contact_id)
            customer_id = customer.id

        try:
            checkout = await payment_service.create_checkout_session(
                amount=amount,
                currency=currency,
                success_url="https://app.crm.local/payments/success",
                cancel_url="https://app.crm.local/payments/cancel",
                user_id=user_id,
                customer_id=customer_id,
                quote_id=quote_id,
            )
        except ValueError as e:
            return {"error": str(e)}

        result = {
            "success": True,
            "checkout_url": checkout.get("checkout_url", ""),
            "checkout_session_id": checkout.get("checkout_session_id", ""),
            "amount": amount,
            "currency": currency,
            "message": f"Payment link created for {currency} {amount:,.2f}.",
        }

        if contact_id and checkout.get("checkout_url"):
            contact_result = await self.db.execute(
                select(Contact).where(Contact.id == contact_id)
            )
            contact = contact_result.scalar_one_or_none()
            if contact and contact.email:
                from src.email.branded_templates import TenantBrandingHelper, render_branded_email
                from src.email.service import EmailService

                branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)
                body_html = (
                    f"<p>Dear {contact.full_name},</p>"
                    f"<p>{description}</p>"
                    f"<p>Amount: <strong>{currency} {amount:,.2f}</strong></p>"
                )
                html = render_branded_email(
                    branding=branding,
                    subject=f"Payment Link - {currency} {amount:,.2f}",
                    headline="Payment Request",
                    body_html=body_html,
                    cta_text="Pay Now",
                    cta_url=checkout["checkout_url"],
                )
                email_service = EmailService(self.db)
                await email_service.queue_email(
                    to_email=contact.email,
                    subject=f"Payment Link - {currency} {amount:,.2f}",
                    body=html,
                    sent_by_id=user_id,
                    entity_type="payments",
                )
                result["email_sent"] = True
                result["message"] += " Link emailed to contact."

        return result

    async def send_invoice(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        from src.payments.models import Payment

        result = await self.db.execute(
            select(Payment).where(Payment.id == args["payment_id"])
        )
        payment = result.scalar_one_or_none()
        if not payment:
            return {"error": f"Payment with ID {args['payment_id']} not found."}

        if payment.status != "succeeded":
            return {"error": f"Payment is in '{payment.status}' status, not 'succeeded'."}

        email_addr = None
        client_name = "Customer"
        if payment.customer_id:
            from src.payments.models import StripeCustomer
            cust_result = await self.db.execute(
                select(StripeCustomer).where(StripeCustomer.id == payment.customer_id)
            )
            customer = cust_result.scalar_one_or_none()
            if customer:
                email_addr = customer.email
                client_name = customer.name or "Customer"

                if not email_addr and customer.contact_id:
                    contact_result = await self.db.execute(
                        select(Contact).where(Contact.id == customer.contact_id)
                    )
                    contact = contact_result.scalar_one_or_none()
                    if contact:
                        email_addr = contact.email
                        client_name = contact.full_name

        if not email_addr:
            return {"error": "No email address found for this payment's customer."}

        from src.email.branded_templates import TenantBrandingHelper, render_payment_receipt_email
        from src.email.service import EmailService

        branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)
        payment_data = {
            "receipt_number": str(payment.id),
            "client_name": client_name,
            "amount": str(float(payment.amount) if payment.amount else "0.00"),
            "currency": payment.currency or "USD",
            "payment_date": payment.created_at.strftime("%Y-%m-%d") if payment.created_at else "",
            "payment_method": payment.payment_method or "Card",
        }
        subject, html_body = render_payment_receipt_email(branding, payment_data)

        email_service = EmailService(self.db)
        await email_service.queue_email(
            to_email=email_addr,
            subject=subject,
            body=html_body,
            sent_by_id=user_id,
            entity_type="payments",
            entity_id=payment.id,
        )

        return {
            "success": True,
            "message": f"Invoice sent to {email_addr} for payment #{payment.id}.",
        }

    async def send_email_to_contact(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        contact_result = await self.db.execute(
            select(Contact).where(Contact.id == args["contact_id"])
        )
        contact = contact_result.scalar_one_or_none()
        if not contact:
            return {"error": f"Contact with ID {args['contact_id']} not found."}
        if not contact.email:
            return {"error": f"Contact '{contact.full_name}' has no email address."}

        subject = args["subject"]
        body = args["body"]
        use_branded = args.get("use_branded_template", True)

        from src.email.service import EmailService
        email_service = EmailService(self.db)

        if use_branded:
            from src.email.branded_templates import TenantBrandingHelper, render_branded_email
            branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)
            html_body = render_branded_email(
                branding=branding,
                subject=subject,
                headline=subject,
                body_html=body,
            )
        else:
            html_body = body

        await email_service.queue_email(
            to_email=contact.email,
            subject=subject,
            body=html_body,
            sent_by_id=user_id,
            entity_type="contacts",
            entity_id=contact.id,
        )

        return {
            "success": True,
            "message": f"Email sent to {contact.full_name} ({contact.email}).",
        }

    async def schedule_follow_up_sequence(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        entity_type = args["entity_type"]
        entity_id = args["entity_id"]
        steps = args.get("steps", [])

        if not steps:
            return {"error": "No steps provided for the follow-up sequence."}

        service = ActivityService(self.db)
        created_activities = []

        for step in steps:
            delay_days = step.get("delay_days", 1)
            due = date.today() + timedelta(days=delay_days)

            activity_data = ActivityCreate(
                subject=step.get("subject", "Follow-up"),
                activity_type=step.get("activity_type", "task"),
                entity_type=entity_type,
                entity_id=entity_id,
                due_date=due,
                priority="normal",
                description=step.get("description", ""),
            )
            activity = await service.create(activity_data, user_id)
            created_activities.append({
                "activity_id": activity.id,
                "subject": activity.subject,
                "type": activity.activity_type,
                "due_date": due.isoformat(),
            })

        return {
            "success": True,
            "activities_created": len(created_activities),
            "activities": created_activities,
            "message": f"Scheduled {len(created_activities)} follow-up activities.",
        }

    async def send_campaign_to_segment(self, args: Dict[str, Any], user_id: int) -> Dict[str, Any]:
        from src.campaigns.models import Campaign

        campaign_result = await self.db.execute(
            select(Campaign).where(Campaign.id == args["campaign_id"])
        )
        campaign = campaign_result.scalar_one_or_none()
        if not campaign:
            return {"error": f"Campaign with ID {args['campaign_id']} not found."}

        campaign.status = "in_progress"
        await self.db.flush()

        return {
            "success": True,
            "campaign_id": campaign.id,
            "campaign_name": campaign.name,
            "status": "in_progress",
            "message": f"Campaign '{campaign.name}' execution started.",
        }

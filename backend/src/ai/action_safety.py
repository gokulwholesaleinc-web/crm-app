"""Action safety classification for AI command execution."""

from enum import Enum
from typing import Dict, Optional


class ActionRisk(Enum):
    READ = "read"
    WRITE_LOW = "write_low"
    WRITE_HIGH = "write_high"
    DESTRUCTIVE = "destructive"


ACTION_CLASSIFICATION: Dict[str, ActionRisk] = {
    # Read operations
    "search_contacts": ActionRisk.READ,
    "search_leads": ActionRisk.READ,
    "get_pipeline_summary": ActionRisk.READ,
    "get_upcoming_tasks": ActionRisk.READ,
    "get_recent_activities": ActionRisk.READ,
    "get_kpis": ActionRisk.READ,
    "generate_pipeline_report": ActionRisk.READ,
    "generate_activity_report": ActionRisk.READ,
    # Low-risk write operations
    "add_note": ActionRisk.WRITE_LOW,
    "create_lead": ActionRisk.WRITE_LOW,
    "create_activity": ActionRisk.WRITE_LOW,
    # High-risk write operations
    "update_lead_status": ActionRisk.WRITE_HIGH,
    "update_opportunity_stage": ActionRisk.WRITE_HIGH,
    # New learning/expanded tools
    "search_quotes": ActionRisk.READ,
    "get_quote_details": ActionRisk.READ,
    "search_proposals": ActionRisk.READ,
    "get_payment_summary": ActionRisk.READ,
    "list_recent_payments": ActionRisk.READ,
    "get_campaign_stats": ActionRisk.READ,
    "get_deal_coaching": ActionRisk.READ,
    "remember_preference": ActionRisk.WRITE_LOW,
    # Pipeline intelligence (safe - read-only analysis)
    "analyze_pipeline": ActionRisk.READ,
    "suggest_improvements": ActionRisk.READ,
    "get_stale_deals": ActionRisk.READ,
    "get_follow_up_priorities": ActionRisk.READ,
    # Execution tools (high-risk - send/create externally)
    "create_and_send_quote": ActionRisk.WRITE_HIGH,
    "resend_quote": ActionRisk.WRITE_HIGH,
    "create_and_send_proposal": ActionRisk.WRITE_HIGH,
    "resend_proposal": ActionRisk.WRITE_HIGH,
    "create_payment_link": ActionRisk.WRITE_HIGH,
    "send_invoice": ActionRisk.WRITE_HIGH,
    "send_email_to_contact": ActionRisk.WRITE_HIGH,
    "schedule_follow_up_sequence": ActionRisk.WRITE_HIGH,
    "send_campaign_to_segment": ActionRisk.WRITE_HIGH,
}


# Human-readable descriptions for confirmation prompts
ACTION_DESCRIPTIONS: Dict[str, str] = {
    "update_lead_status": "Change the status of lead #{lead_id} to '{new_status}'",
    "update_opportunity_stage": "Move opportunity #{opportunity_id} to a new pipeline stage",
    "create_and_send_quote": "Create a quote titled '{title}' for contact #{contact_id} and send it",
    "resend_quote": "Resend quote #{quote_id} to the client",
    "create_and_send_proposal": "Generate a proposal for opportunity #{opportunity_id} and send it",
    "resend_proposal": "Resend proposal #{proposal_id} to the client",
    "create_payment_link": "Create a payment link for ${amount} {currency}",
    "send_invoice": "Send an invoice for payment #{payment_id}",
    "send_email_to_contact": "Send an email to contact #{contact_id} with subject '{subject}'",
    "schedule_follow_up_sequence": "Schedule a multi-step follow-up sequence for {entity_type} #{entity_id}",
    "send_campaign_to_segment": "Send campaign #{campaign_id} to segment '{segment}'",
}


def classify_action(function_name: str) -> ActionRisk:
    """Get the risk classification for a function."""
    return ACTION_CLASSIFICATION.get(function_name, ActionRisk.READ)


def requires_confirmation(function_name: str) -> bool:
    """Check if an action requires user confirmation before execution."""
    risk = classify_action(function_name)
    return risk in (ActionRisk.WRITE_HIGH, ActionRisk.DESTRUCTIVE)


def get_confirmation_description(function_name: str, args: dict) -> Optional[str]:
    """Get a human-readable description of a high-risk action for confirmation."""
    template = ACTION_DESCRIPTIONS.get(function_name)
    if template:
        try:
            return template.format(**args)
        except KeyError:
            return f"Execute {function_name} with arguments: {args}"
    return f"Execute {function_name} with arguments: {args}"

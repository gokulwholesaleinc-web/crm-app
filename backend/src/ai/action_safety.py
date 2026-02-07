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
}


# Human-readable descriptions for confirmation prompts
ACTION_DESCRIPTIONS: Dict[str, str] = {
    "update_lead_status": "Change the status of lead #{lead_id} to '{new_status}'",
    "update_opportunity_stage": "Move opportunity #{opportunity_id} to a new pipeline stage",
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

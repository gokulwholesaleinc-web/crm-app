"""Embedding hooks for entity CRUD operations."""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.embeddings import EmbeddingService
from src.config import settings

logger = logging.getLogger(__name__)


def _safe_str(value: Any) -> str:
    """Convert value to string, returning empty string if None."""
    return str(value) if value is not None else ""


def build_contact_embedding_content(contact: Any, company_name: str | None = None) -> str:
    """Build embedding content for a contact.

    Format: {first_name} {last_name} - {job_title} at {company_name}. {description}
    """
    parts = [f"{_safe_str(contact.first_name)} {_safe_str(contact.last_name)}"]

    job_company_parts = []
    if contact.job_title:
        job_company_parts.append(_safe_str(contact.job_title))

    # Use provided company_name or try to get from relationship
    comp_name = company_name
    if comp_name is None and hasattr(contact, 'company') and contact.company:
        comp_name = contact.company.name

    if comp_name:
        if job_company_parts:
            job_company_parts.append(f"at {comp_name}")
        else:
            job_company_parts.append(comp_name)

    if job_company_parts:
        parts.append(" - " + " ".join(job_company_parts))

    if contact.description:
        parts.append(f". {_safe_str(contact.description)}")

    return "".join(parts).strip()


def build_company_embedding_content(company: Any) -> str:
    """Build embedding content for a company.

    Format: {name} - {industry}. {description}
    """
    parts = [_safe_str(company.name)]

    if company.industry:
        parts.append(f" - {_safe_str(company.industry)}")

    if company.description:
        parts.append(f". {_safe_str(company.description)}")

    return "".join(parts).strip()


def build_lead_embedding_content(lead: Any) -> str:
    """Build embedding content for a lead.

    Format: {first_name} {last_name} - {company_name}. {description}
    """
    parts = [f"{_safe_str(lead.first_name)} {_safe_str(lead.last_name)}"]

    if lead.company_name:
        parts.append(f" - {_safe_str(lead.company_name)}")

    if lead.description:
        parts.append(f". {_safe_str(lead.description)}")

    return "".join(parts).strip()


def build_opportunity_embedding_content(opportunity: Any) -> str:
    """Build embedding content for an opportunity.

    Format: {name} - ${amount} - {stage}. {description}
    """
    parts = [_safe_str(opportunity.name)]

    if opportunity.amount:
        parts.append(f" - ${opportunity.amount:,.2f}")

    # Get stage name from relationship
    if hasattr(opportunity, 'pipeline_stage') and opportunity.pipeline_stage:
        parts.append(f" - {_safe_str(opportunity.pipeline_stage.name)}")

    if opportunity.description:
        parts.append(f". {_safe_str(opportunity.description)}")

    return "".join(parts).strip()


async def store_entity_embedding(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
    content: str,
) -> None:
    """No-op while the AI assistant is disabled.

    The 28 call-sites scattered across leads/contacts/opportunities/etc.
    routers were left in place intentionally so re-enabling the AI
    assistant in the future just requires reverting this body. With the
    function as a no-op, no OpenAI calls fire on every CRUD write —
    eliminating recurring spend during the AI-overhaul gap.

    Original implementation lives in git history; restore by reverting
    the commit that disabled it.
    """
    return


async def delete_entity_embedding(
    db: AsyncSession,
    entity_type: str,
    entity_id: int,
) -> None:
    """Delete embedding for an entity. Fails silently on error.

    This function is designed to be non-blocking - it will not raise exceptions
    that would disrupt the main CRUD operation.
    """
    import os
    if not (settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")):
        return

    try:
        embedding_service = EmbeddingService(db)
        await embedding_service.delete_embedding(
            entity_type=entity_type,
            entity_id=entity_id,
        )
        logger.debug(f"Deleted embedding for {entity_type}:{entity_id}")
    except Exception as e:
        # Log but don't fail the main operation
        logger.warning(f"Failed to delete embedding for {entity_type}:{entity_id}: {e}")

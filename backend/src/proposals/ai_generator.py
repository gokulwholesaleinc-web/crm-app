"""AI-powered proposal generation using OpenAI GPT-4."""

import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.proposals.models import Proposal
from src.proposals.service import ProposalService
from src.proposals.schemas import ProposalCreate
from src.opportunities.models import Opportunity
from src.quotes.models import Quote

logger = logging.getLogger(__name__)


async def generate_proposal(
    db: AsyncSession, opportunity_id: int, user_id: int
) -> Proposal:
    """Generate a proposal using AI based on opportunity data.

    Loads the opportunity, contact, company, and linked quote data,
    then sends to GPT-4 to generate proposal content sections.

    Args:
        db: Database session
        opportunity_id: ID of the opportunity to generate proposal for
        user_id: ID of the user creating the proposal

    Returns:
        The created Proposal record with AI-generated content

    Raises:
        ValueError: If opportunity not found or OPENAI_API_KEY not set
    """
    # Load opportunity with related data
    result = await db.execute(
        select(Opportunity)
        .options(
            selectinload(Opportunity.contact),
            selectinload(Opportunity.company),
            selectinload(Opportunity.pipeline_stage),
        )
        .where(Opportunity.id == opportunity_id)
    )
    opportunity = result.scalar_one_or_none()
    if not opportunity:
        raise ValueError(f"Opportunity with ID {opportunity_id} not found")

    # Load linked quote if exists
    quote_result = await db.execute(
        select(Quote)
        .options(selectinload(Quote.line_items))
        .where(Quote.opportunity_id == opportunity_id)
        .order_by(Quote.created_at.desc())
        .limit(1)
    )
    quote = quote_result.scalar_one_or_none()

    # Build context for AI
    contact_name = "the prospect"
    company_name = "the company"
    if opportunity.contact:
        contact_name = opportunity.contact.full_name
    if opportunity.company:
        company_name = opportunity.company.name

    deal_amount = opportunity.amount or 0
    deal_name = opportunity.name
    deal_description = opportunity.description or ""

    # Build pricing context from quote
    pricing_context = ""
    quote_id = None
    if quote:
        quote_id = quote.id
        pricing_context = f"\nExisting Quote ({quote.quote_number}):\n"
        pricing_context += f"  Total: ${quote.total:,.2f}\n"
        for item in quote.line_items:
            pricing_context += f"  - {item.description}: {item.quantity} x ${item.unit_price:,.2f} = ${item.total:,.2f}\n"

    # Check if OpenAI API key is configured
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set, generating placeholder proposal")
        return await _create_placeholder_proposal(
            db, opportunity, contact_name, company_name,
            deal_amount, deal_name, deal_description,
            pricing_context, quote_id, user_id,
        )

    # Generate with OpenAI
    try:
        return await _generate_with_openai(
            db, opportunity, contact_name, company_name,
            deal_amount, deal_name, deal_description,
            pricing_context, quote_id, user_id,
        )
    except Exception as e:
        logger.error(f"OpenAI generation failed: {e}, falling back to placeholder")
        return await _create_placeholder_proposal(
            db, opportunity, contact_name, company_name,
            deal_amount, deal_name, deal_description,
            pricing_context, quote_id, user_id,
        )


async def _generate_with_openai(
    db: AsyncSession,
    opportunity: Opportunity,
    contact_name: str,
    company_name: str,
    deal_amount: float,
    deal_name: str,
    deal_description: str,
    pricing_context: str,
    quote_id: Optional[int],
    user_id: int,
) -> Proposal:
    """Generate proposal sections using OpenAI GPT-4."""
    import openai

    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    prompt = f"""Generate a professional sales proposal for the following opportunity:

Opportunity: {deal_name}
Description: {deal_description}
Contact: {contact_name}
Company: {company_name}
Deal Value: ${deal_amount:,.2f}
{pricing_context}

Please generate the following sections. Use a professional tone tailored to {company_name}.
Format each section clearly.

1. EXECUTIVE SUMMARY (2-3 paragraphs tailored to the prospect's needs)
2. SCOPE OF WORK (detailed bullet points of deliverables)
3. PRICING SECTION (formatted pricing breakdown based on the quote data if available, otherwise estimate based on deal value)
4. TIMELINE (estimated project timeline with milestones)

Separate each section with the delimiter: ---SECTION---"""

    response = await client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a professional sales proposal writer. Generate clear, compelling proposal content."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=2000,
    )

    ai_content = response.choices[0].message.content or ""
    sections = ai_content.split("---SECTION---")

    executive_summary = sections[0].strip() if len(sections) > 0 else ""
    scope_of_work = sections[1].strip() if len(sections) > 1 else ""
    pricing_section = sections[2].strip() if len(sections) > 2 else ""
    timeline_section = sections[3].strip() if len(sections) > 3 else ""

    # Clean up section headers
    for header in ["EXECUTIVE SUMMARY", "1.", "1)"]:
        executive_summary = executive_summary.replace(header, "").strip()
    for header in ["SCOPE OF WORK", "2.", "2)"]:
        scope_of_work = scope_of_work.replace(header, "").strip()
    for header in ["PRICING SECTION", "PRICING", "3.", "3)"]:
        pricing_section = pricing_section.replace(header, "").strip()
    for header in ["TIMELINE", "4.", "4)"]:
        timeline_section = timeline_section.replace(header, "").strip()

    proposal_data = ProposalCreate(
        title=f"Proposal for {deal_name}",
        content=ai_content,
        opportunity_id=opportunity.id,
        contact_id=opportunity.contact_id,
        company_id=opportunity.company_id,
        quote_id=quote_id,
        executive_summary=executive_summary,
        scope_of_work=scope_of_work,
        pricing_section=pricing_section,
        timeline=timeline_section,
        owner_id=user_id,
    )

    service = ProposalService(db)
    return await service.create(proposal_data, user_id)


async def _create_placeholder_proposal(
    db: AsyncSession,
    opportunity: Opportunity,
    contact_name: str,
    company_name: str,
    deal_amount: float,
    deal_name: str,
    deal_description: str,
    pricing_context: str,
    quote_id: Optional[int],
    user_id: int,
) -> Proposal:
    """Create a proposal with placeholder content when OpenAI is unavailable."""
    executive_summary = (
        f"We are pleased to present this proposal for {deal_name} to {company_name}. "
        f"Based on our discussions with {contact_name}, we have prepared a comprehensive "
        f"solution tailored to your specific requirements.\n\n"
        f"{deal_description}"
    )

    scope_of_work = (
        f"Deliverables for {deal_name}:\n"
        f"- Requirements analysis and planning\n"
        f"- Solution design and implementation\n"
        f"- Testing and quality assurance\n"
        f"- Deployment and go-live support\n"
        f"- Documentation and training"
    )

    pricing_section = f"Total Investment: ${deal_amount:,.2f}\n"
    if pricing_context:
        pricing_section += pricing_context

    timeline_section = (
        "Estimated Timeline:\n"
        "- Week 1-2: Discovery and Planning\n"
        "- Week 3-6: Implementation\n"
        "- Week 7-8: Testing and QA\n"
        "- Week 9: Deployment and Go-Live"
    )

    proposal_data = ProposalCreate(
        title=f"Proposal for {deal_name}",
        content=f"{executive_summary}\n\n{scope_of_work}\n\n{pricing_section}\n\n{timeline_section}",
        opportunity_id=opportunity.id,
        contact_id=opportunity.contact_id,
        company_id=opportunity.company_id,
        quote_id=quote_id,
        executive_summary=executive_summary,
        scope_of_work=scope_of_work,
        pricing_section=pricing_section,
        timeline=timeline_section,
        owner_id=user_id,
    )

    service = ProposalService(db)
    return await service.create(proposal_data, user_id)

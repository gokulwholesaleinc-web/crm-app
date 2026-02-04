"""Lead scoring algorithm."""

import json
from typing import Dict, Tuple
from src.leads.models import Lead


class LeadScorer:
    """
    Lead scoring system based on multiple factors.

    Scoring factors and weights:
    - Completeness of profile (0-20 points)
    - Company information (0-15 points)
    - Budget specified (0-20 points)
    - Industry match (0-15 points)
    - Source quality (0-15 points)
    - Engagement (0-15 points)
    """

    # Industry priority for B2B SaaS (customize as needed)
    PRIORITY_INDUSTRIES = [
        "Technology",
        "Software",
        "Financial Services",
        "Healthcare",
        "Manufacturing",
    ]

    # High-quality lead sources
    HIGH_QUALITY_SOURCES = [
        "Referral",
        "Website - Contact Form",
        "Demo Request",
        "Trade Show",
    ]

    MEDIUM_QUALITY_SOURCES = [
        "Website - Download",
        "Webinar",
        "LinkedIn",
        "Partner",
    ]

    def calculate_score(self, lead: Lead, source_name: str = None) -> Tuple[int, Dict]:
        """
        Calculate lead score and return score with breakdown.

        Returns:
            Tuple of (total_score, score_factors_dict)
        """
        factors = {}

        # Profile completeness (0-20)
        profile_score = self._score_profile_completeness(lead)
        factors["profile_completeness"] = profile_score

        # Company info (0-15)
        company_score = self._score_company_info(lead)
        factors["company_info"] = company_score

        # Budget (0-20)
        budget_score = self._score_budget(lead)
        factors["budget"] = budget_score

        # Industry match (0-15)
        industry_score = self._score_industry(lead)
        factors["industry"] = industry_score

        # Source quality (0-15)
        source_score = self._score_source(source_name)
        factors["source_quality"] = source_score

        # Engagement placeholder (0-15) - can be updated based on activity
        engagement_score = 0
        factors["engagement"] = engagement_score

        total_score = sum(factors.values())
        return total_score, factors

    def _score_profile_completeness(self, lead: Lead) -> int:
        """Score based on how complete the lead profile is."""
        score = 0
        fields = [
            (lead.email, 5),
            (lead.phone or lead.mobile, 4),
            (lead.job_title, 4),
            (lead.first_name and lead.last_name, 4),
            (lead.description, 3),
        ]
        for field_value, points in fields:
            if field_value:
                score += points
        return min(score, 20)

    def _score_company_info(self, lead: Lead) -> int:
        """Score based on company information."""
        score = 0
        if lead.company_name:
            score += 5
        if lead.website:
            score += 5
        if lead.industry:
            score += 5
        return min(score, 15)

    def _score_budget(self, lead: Lead) -> int:
        """Score based on budget information."""
        if not lead.budget_amount:
            return 0

        # Tiered scoring based on budget
        if lead.budget_amount >= 100000:
            return 20
        elif lead.budget_amount >= 50000:
            return 15
        elif lead.budget_amount >= 10000:
            return 10
        elif lead.budget_amount >= 1000:
            return 5
        return 2

    def _score_industry(self, lead: Lead) -> int:
        """Score based on industry match."""
        if not lead.industry:
            return 0

        industry_lower = lead.industry.lower()
        for priority_industry in self.PRIORITY_INDUSTRIES:
            if priority_industry.lower() in industry_lower:
                return 15

        # Partial match
        return 5

    def _score_source(self, source_name: str = None) -> int:
        """Score based on lead source quality."""
        if not source_name:
            return 0

        source_lower = source_name.lower()

        for high_source in self.HIGH_QUALITY_SOURCES:
            if high_source.lower() in source_lower:
                return 15

        for medium_source in self.MEDIUM_QUALITY_SOURCES:
            if medium_source.lower() in source_lower:
                return 10

        return 5


def calculate_lead_score(lead: Lead, source_name: str = None) -> Tuple[int, str]:
    """
    Convenience function to calculate lead score.

    Returns:
        Tuple of (score, score_factors_json_string)
    """
    scorer = LeadScorer()
    score, factors = scorer.calculate_score(lead, source_name)
    return score, json.dumps(factors)

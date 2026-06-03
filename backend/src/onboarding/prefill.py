"""Single source of truth for the onboarding prefill allow-list.

Lives in its own leaf module (imports nothing from the onboarding package) so
BOTH the esign coords validator and the v3 questionnaire validator can reuse the
SAME set without a circular import. ``email`` is deliberately absent — contact
PII is never prefillable (spec §7.2). Any ``prefill`` source outside this set is
rejected at template-save time by every kind's ``validate_definitions``.
"""

from __future__ import annotations

# The only fields a template author may auto-populate from CRM data. NEVER add
# ``contact.email`` (or any PII) here — see the prefill-PII rule (§D.5).
ALLOWED_PREFILL: frozenset[str] = frozenset({"contact.name", "company.name"})

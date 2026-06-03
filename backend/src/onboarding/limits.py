"""Onboarding abuse-cap constants (leaf module — imports nothing).

Single source of truth so the kind handlers can reuse the same per-field byte
cap as ``packet_service`` without importing that heavy module (which would drag
the app router graph into the ``kinds`` import chain). See §6 abuse caps.
"""

from __future__ import annotations

# Max UTF-8 bytes for a single text field value.
MAX_TEXT_VALUE_BYTES = 4 * 1024
# Max number of fields accepted in one PATCH body.
MAX_FIELD_COUNT = 200

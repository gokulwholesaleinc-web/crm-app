"""Money + micros normalization — pure ``Decimal`` helpers (A4 / NN-8).

Every monetary or conversion amount in the warehouse is ``Decimal`` end to end —
never float (binary rounding corrupts Cost/Conv, ROAS) and never int (Google
reports fractional conversions; truncation corrupts the same ratios). These two
helpers are the single place platform amounts become comparable:

* Google Ads reports money as **micros** (``cost_micros``) → ÷ 1,000,000.
* Meta reports money as a decimal string of account-currency units → parse as-is.

So ``from_micros(5_000_000) == to_money("5.00")`` — the A4 comparability invariant
the C2 gating test asserts. Both quantize to 6 fractional places to match the
``Numeric(18, 6)`` fact columns exactly (no surprise re-rounding at the DB).

Leaf module (stdlib only) so ingest mappers and the warehouse share one source of
truth without dragging the app graph into their import chain.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_MICROS = Decimal(1_000_000)
_Q6 = Decimal("0.000001")


def _to_decimal(value: Decimal | int | str | float) -> Decimal:
    """Coerce to ``Decimal`` safely — floats go through ``str`` to avoid binary
    artifacts (``Decimal(0.1)`` ≠ ``Decimal("0.1")``)."""
    # bool is a subclass of int, so a stray JSON ``true``/``false`` reaching a money
    # field would silently become 1.00 / 0.00. Refuse it loudly (must precede the
    # int path since isinstance(True, int) is True).
    if isinstance(value, bool):
        raise TypeError(f"refusing to coerce bool to a money/conversion Decimal: {value!r}")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def q6(value: Decimal | int | str | float) -> Decimal:
    """Quantize to the fact columns' 6-place scale (half-up)."""
    return _to_decimal(value).quantize(_Q6, rounding=ROUND_HALF_UP)


def from_micros(micros: int | str | Decimal | None) -> Decimal:
    """Google Ads micros → account-currency ``Decimal`` (÷ 1e6), 6-place scaled.

    ``None`` → ``0.000000`` (a missing measure is zero, not null, in a fact row).
    """
    if micros is None:
        return Decimal("0.000000")
    return (_to_decimal(micros) / _MICROS).quantize(_Q6, rounding=ROUND_HALF_UP)


def to_money(value: Decimal | int | str | float | None) -> Decimal:
    """Parse an already-in-currency amount (Meta spend string, a budget) to a
    6-place ``Decimal``. ``None`` → ``0.000000``."""
    if value is None:
        return Decimal("0.000000")
    return q6(value)

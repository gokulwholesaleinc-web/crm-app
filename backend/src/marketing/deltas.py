"""Period-over-period delta math — settled-window + per-metric direction (A6).

The vendor showed a bare ▲/▼ % with no notion of "good vs bad direction" and a
``100%`` jump out of a zero baseline. PART III A6 forbids reusing
``dashboard.number_cards._calculate_change`` raw for exactly those two reasons:

* It is **direction-agnostic** — a rising CPC reads as a green ▲ when it is bad.
* It returns ``100.0`` for a zero baseline — a fake "+100%" instead of "New".

These are pure functions (no DB, no I/O) so they are exhaustively unit-tested.
They take *already-aggregated, already-settled* scalars from ``reads`` /
``service`` — the settled-window exclusion (dropping the most recent provisional
days symmetrically from BOTH compare windows, A6) happens at the window-math
layer (``window_bounds``) before the sums are taken, so this module only has to
encode direction + zero-baseline + divide-by-zero semantics.

Contract for a single delta result (mirrored into ``schemas.MetricDelta``):
* ``pct``      — signed percentage change, or ``None`` (no prior data / withheld).
* ``direction``— ``"up"`` / ``"down"`` / ``"flat"`` (raw movement of the value).
* ``is_good``  — whether that movement is favorable for THIS metric (CPC down is
  good); ``None`` when undecidable (zero baseline, or a metric with no polarity).
* ``is_new``   — ``True`` when there is no prior-period baseline to compare against
  (render "New", never "+100%").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

# Metrics where a DECREASE is the good outcome (cost efficiency). Everything not
# listed is "up is good" (spend is neutral-but-treated-up; volume/value/rate up
# is good). Keyed by the canonical metric id used across reads/schemas.
COST_EFFICIENCY_METRICS: frozenset[str] = frozenset(
    {
        "cpc",
        "cost_per_conversion",
        "cost_per_purchase",
        "cpp",
        "cpm",
        "cpa",
        "bounce_rate",
        "position",  # GSC average position: lower (closer to 1) is better
    }
)

# Metrics with no inherent good/bad polarity — movement is informational only.
NEUTRAL_METRICS: frozenset[str] = frozenset({"spend", "cost", "impressions", "reach"})

_Number = int | float | Decimal


@dataclass(frozen=True, slots=True)
class MetricDelta:
    """A computed period-over-period delta for one metric."""

    pct: float | None
    direction: str  # "up" | "down" | "flat"
    is_good: bool | None
    is_new: bool


def _to_decimal(value: _Number | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    # Route floats through str so 0.1 stays 0.1 (no binary artifacts).
    return Decimal(str(value))


def compute_delta(
    metric: str,
    current: _Number | None,
    previous: _Number | None,
) -> MetricDelta:
    """Period-over-period delta for ``metric`` with direction + zero-baseline rules.

    * ``previous`` is ``None``/``0`` and ``current`` has a value → ``is_new`` (no
      baseline; UI renders "New", **never** ``+100%`` like ``_calculate_change``).
    * Both sides ``None``/``0`` → flat, ``pct=None`` (nothing happened — em-dash).
    * ÷0 is impossible here because a zero ``previous`` short-circuits to ``is_new``.
    * ``is_good`` inverts for cost-efficiency metrics (CPC/Cost-per-X/position/
      bounce down = good); ``None`` for neutral metrics or an undecidable baseline.
    """
    cur = _to_decimal(current)
    prev = _to_decimal(previous)

    cur_zero = cur is None or cur == 0
    prev_zero = prev is None or prev == 0

    if prev_zero:
        if cur_zero:
            # No movement and no baseline → truly nothing to compare.
            return MetricDelta(pct=None, direction="flat", is_good=None, is_new=False)
        # Rose from a zero/absent baseline → "New", not a fabricated +100%.
        return MetricDelta(pct=None, direction="up", is_good=None, is_new=True)

    # prev is a real non-zero number from here on → division is safe.
    assert prev is not None
    cur_val = cur if cur is not None else Decimal(0)
    pct = float((cur_val - prev) / prev * 100)
    pct = round(pct, 1)

    if pct > 0:
        direction = "up"
    elif pct < 0:
        direction = "down"
    else:
        direction = "flat"

    is_good = _direction_is_good(metric, direction)
    return MetricDelta(pct=pct, direction=direction, is_good=is_good, is_new=False)


def _direction_is_good(metric: str, direction: str) -> bool | None:
    """Whether ``direction`` of movement is favorable for ``metric`` (A6)."""
    if direction == "flat":
        return None
    if metric in NEUTRAL_METRICS:
        return None
    rose = direction == "up"
    if metric in COST_EFFICIENCY_METRICS:
        # Down is good → good when it did NOT rise.
        return not rose
    # Default "up is good".
    return rose


def settled_window_end(
    date_to: date,
    *,
    provisional_days: int,
) -> date:
    """Trim the most recent ``provisional_days`` from a window's end (A6).

    Recent ad/analytics days are provisional (attribution still settling), so
    delta math compares only fully-settled days. The SAME trim is applied
    symmetrically to both the current and the compare window so neither side is
    advantaged by including or excluding provisional tails.
    """
    if provisional_days <= 0:
        return date_to
    return date_to - timedelta(days=provisional_days)


def default_compare_window(
    date_from: date, date_to: date
) -> tuple[date, date]:
    """The prior equal-length period immediately preceding ``[date_from, date_to]``.

    Inclusive bounds: a 7-day window ``[Jun 8 .. Jun 14]`` compares against
    ``[Jun 1 .. Jun 7]`` (same 7 days, no overlap, no gap).
    """
    span = (date_to - date_from).days
    compare_to = date_from - timedelta(days=1)
    compare_from = compare_to - timedelta(days=span)
    return compare_from, compare_to

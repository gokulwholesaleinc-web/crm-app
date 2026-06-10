"""A6 delta math — per-metric direction, zero-baseline → "New", settled windows.

Pure functions, no DB. Guards the two things PART III A6 forbids reusing
``_calculate_change`` for: direction-agnostic deltas and a fake +100% from a
zero baseline.
"""

from datetime import date

from src.marketing.deltas import (
    compute_delta,
    default_compare_window,
    settled_window_end,
)


class TestComputeDelta:
    def test_increase_is_up_and_signed(self):
        d = compute_delta("clicks", 120, 100)
        assert d.pct == 20.0
        assert d.direction == "up"
        assert d.is_good is True  # more clicks is good
        assert d.is_new is False

    def test_cost_efficiency_metric_inverts_direction(self):
        # CPC rising is BAD even though the value went up.
        d = compute_delta("cpc", 2.0, 1.0)
        assert d.direction == "up"
        assert d.is_good is False
        # CPC falling is GOOD.
        d2 = compute_delta("cpc", 0.5, 1.0)
        assert d2.direction == "down"
        assert d2.is_good is True

    def test_gsc_position_lower_is_better(self):
        # Average position moving from 5 -> 3 is an improvement (down is good).
        d = compute_delta("position", 3, 5)
        assert d.direction == "down"
        assert d.is_good is True

    def test_zero_baseline_is_new_not_100pct(self):
        d = compute_delta("conversions", 5, 0)
        assert d.is_new is True
        assert d.pct is None  # never a fabricated +100%
        assert d.direction == "up"

    def test_none_baseline_is_new(self):
        d = compute_delta("spend", 10, None)
        assert d.is_new is True
        assert d.pct is None

    def test_both_zero_is_flat_with_no_pct(self):
        d = compute_delta("conversions", 0, 0)
        assert d.is_new is False
        assert d.pct is None
        assert d.direction == "flat"

    def test_neutral_metric_has_no_polarity(self):
        d = compute_delta("spend", 200, 100)
        assert d.direction == "up"
        assert d.is_good is None  # spend has no inherent good/bad

    def test_decrease_is_down(self):
        d = compute_delta("clicks", 80, 100)
        assert d.pct == -20.0
        assert d.direction == "down"
        assert d.is_good is False


class TestSettledWindow:
    def test_trims_provisional_tail(self):
        assert settled_window_end(date(2026, 6, 14), provisional_days=3) == date(2026, 6, 11)

    def test_zero_provisional_is_noop(self):
        assert settled_window_end(date(2026, 6, 14), provisional_days=0) == date(2026, 6, 14)


class TestDefaultCompareWindow:
    def test_prior_equal_length_period_no_overlap(self):
        # [Jun 8 .. Jun 14] (7 days) compares against [Jun 1 .. Jun 7].
        cf, ct = default_compare_window(date(2026, 6, 8), date(2026, 6, 14))
        assert ct == date(2026, 6, 7)
        assert cf == date(2026, 6, 1)
        # same length, immediately preceding, no gap, no overlap
        assert (ct - cf).days == (date(2026, 6, 14) - date(2026, 6, 8)).days

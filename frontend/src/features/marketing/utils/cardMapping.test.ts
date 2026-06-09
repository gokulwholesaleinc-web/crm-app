import { describe, it, expect } from 'vitest';
import type { MetricCard } from '../../../api/marketing';
import { formatCardValue, toKpiDelta } from './cardMapping';

const card = (over: Partial<MetricCard>): MetricCard => ({
  key: 'spend',
  label: 'Total Spend',
  value: 100,
  format: 'currency',
  delta: null,
  timeframe: null,
  ...over,
});

describe('cardMapping', () => {
  it('formats by card.format', () => {
    expect(formatCardValue(card({ value: 1234.5, format: 'currency' }), 'USD')).toBe('$1,234.50');
    expect(formatCardValue(card({ value: 3.2, format: 'ratio' }), 'USD')).toBe('3.20');
    expect(formatCardValue(card({ value: 0.15, format: 'percent' }), 'USD')).toBe('15%');
    expect(formatCardValue(card({ value: 1500, format: 'number' }), 'USD')).toBe('1,500');
  });

  it('converts server percent (20.0) to a ratio (0.2) and maps sentiment', () => {
    const d = toKpiDelta(card({ delta: { pct: 20, direction: 'up', is_good: true, is_new: false } }));
    expect(d).toEqual({ pct: 0.2, sentiment: 'good', isNew: false });
  });

  it('maps is_good=false → bad and null → neutral', () => {
    expect(toKpiDelta(card({ delta: { pct: 5, direction: 'up', is_good: false, is_new: false } }))?.sentiment).toBe('bad');
    expect(toKpiDelta(card({ delta: { pct: 5, direction: 'up', is_good: null, is_new: false } }))?.sentiment).toBe('neutral');
  });

  it('preserves the "New" zero-baseline (null pct, isNew true)', () => {
    const d = toKpiDelta(card({ delta: { pct: null, direction: 'up', is_good: null, is_new: true } }));
    expect(d).toEqual({ pct: null, sentiment: 'neutral', isNew: true });
  });

  it('returns null when there is no delta', () => {
    expect(toKpiDelta(card({ delta: null }))).toBeNull();
  });
});

import { describe, it, expect } from 'vitest';
import {
  formatCurrency,
  formatPercent,
  formatSignedPercent,
  formatNumber,
  formatDecimal,
  formatDate,
  formatRelativeTime,
  EM_DASH,
} from './format';

describe('marketing formatters', () => {
  it('formats currency and accepts server Decimal strings', () => {
    expect(formatCurrency(1234.5)).toBe('$1,234.50');
    expect(formatCurrency('1234.5')).toBe('$1,234.50');
    expect(formatCurrency(1234, 'USD', true)).toBe('$1.2K');
  });

  it('renders an em-dash for null/undefined/NaN, never NaN%/Infinity', () => {
    expect(formatCurrency(null)).toBe(EM_DASH);
    expect(formatPercent(undefined)).toBe(EM_DASH);
    expect(formatNumber('')).toBe(EM_DASH);
    expect(formatDecimal(Number.POSITIVE_INFINITY)).toBe(EM_DASH);
  });

  it('treats percent input as a ratio (0.15 -> 15%)', () => {
    expect(formatPercent(0.15)).toBe('15%');
    expect(formatPercent('0.155')).toBe('15.5%');
  });

  it('signs deltas explicitly (never color-alone)', () => {
    expect(formatSignedPercent(0.2)).toBe('+20%');
    expect(formatSignedPercent(-0.2)).toBe('-20%');
    expect(formatSignedPercent(0)).toBe('0%');
  });

  it('formats counts compact for cards', () => {
    expect(formatNumber(1500000)).toBe('1,500,000');
    expect(formatNumber(1500000, true)).toBe('1.5M');
  });

  it('renders a date-only ISO string as the same calendar day regardless of local TZ (C3)', () => {
    // Without timeZone:'UTC' this returns "May 31" under a negative-offset zone.
    expect(formatDate('2026-06-01')).toBe('Jun 1');
    expect(formatDate('2026-06-01', true)).toBe('Jun 1, 2026');
    expect(formatDate(null)).toBe(EM_DASH);
  });

  it('renders relative freshness from a real timestamp', () => {
    const now = new Date('2026-06-08T12:00:00Z');
    expect(formatRelativeTime(new Date('2026-06-08T11:59:30Z'), now)).toBe('just now');
    expect(formatRelativeTime(new Date('2026-06-08T11:30:00Z'), now)).toBe('30m ago');
    expect(formatRelativeTime(new Date('2026-06-08T09:00:00Z'), now)).toBe('3h ago');
    expect(formatRelativeTime(new Date('2026-06-06T12:00:00Z'), now)).toBe('2d ago');
    expect(formatRelativeTime(null, now)).toBe('never');
  });
});

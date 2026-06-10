import { describe, it, expect } from 'vitest';
import { presetRange, compareRange, isValidPreset } from './dateRange';

const TODAY = new Date('2026-06-08T15:30:00Z');

describe('dateRange', () => {
  it('builds inclusive preset windows ending today', () => {
    expect(presetRange('7d', TODAY)).toEqual({ date_from: '2026-06-02', date_to: '2026-06-08' });
    expect(presetRange('30d', TODAY)).toEqual({ date_from: '2026-05-10', date_to: '2026-06-08' });
  });

  it('All spans ~13 months for YoY headroom', () => {
    const r = presetRange('all', TODAY);
    expect(r.date_to).toBe('2026-06-08');
    expect(new Date(r.date_from).getUTCFullYear()).toBe(2025);
  });

  it('compare window is the prior equal-length period with no overlap', () => {
    const r = { date_from: '2026-06-02', date_to: '2026-06-08' }; // 7 days
    expect(compareRange(r)).toEqual({ date_from: '2026-05-26', date_to: '2026-06-01' });
  });

  it('validates presets', () => {
    expect(isValidPreset('30d')).toBe(true);
    expect(isValidPreset('custom')).toBe(true);
    expect(isValidPreset('weekly')).toBe(false);
    expect(isValidPreset(null)).toBe(false);
  });
});

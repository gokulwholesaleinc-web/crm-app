import { describe, expect, it } from 'vitest';
import { parseLooseInt } from './companyFormHelpers';

// Before this helper landed, `parseInt("1,000,000", 10)` returned 1 —
// six zeros silently dropped from a company's annual revenue. The
// helper strips commas/currency/whitespace before Number() so
// user-typed formats survive the round-trip.
describe('parseLooseInt', () => {
  it('parses unformatted integers', () => {
    expect(parseLooseInt('1000000')).toBe(1000000);
  });

  it('strips commas so "1,000,000" no longer rounds to 1', () => {
    expect(parseLooseInt('1,000,000')).toBe(1000000);
  });

  it('strips $ and whitespace', () => {
    expect(parseLooseInt('$ 5,000')).toBe(5000);
  });

  it('preserves negative numbers (e.g. for revenue declines)', () => {
    expect(parseLooseInt('-1,500')).toBe(-1500);
  });

  it('returns null for empty / whitespace / non-numeric', () => {
    expect(parseLooseInt('')).toBeNull();
    expect(parseLooseInt('   ')).toBeNull();
    expect(parseLooseInt('abc')).toBeNull();
    expect(parseLooseInt('-')).toBeNull();
  });

  it('truncates decimals (revenue/employee_count are int columns)', () => {
    expect(parseLooseInt('100.99')).toBe(10099);
  });
});

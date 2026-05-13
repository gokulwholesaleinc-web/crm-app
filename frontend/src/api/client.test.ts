import { describe, expect, it } from 'vitest';
import { flattenErrorDetail } from './client';

describe('flattenErrorDetail', () => {
  it('returns trimmed strings unchanged', () => {
    expect(flattenErrorDetail('  bad email  ')).toBe('bad email');
  });

  it('returns undefined for empty / whitespace strings so callers can fall through', () => {
    expect(flattenErrorDetail('')).toBeUndefined();
    expect(flattenErrorDetail('   ')).toBeUndefined();
  });

  it('joins FastAPI 422 detail-array msgs with "; "', () => {
    const detail = [
      { loc: ['body', 'email'], msg: 'value is not a valid email address', type: 'value_error.email' },
      { loc: ['body', 'phone'], msg: 'string too short', type: 'value_error.any_str.min_length' },
    ];
    expect(flattenErrorDetail(detail)).toBe(
      'value is not a valid email address; string too short',
    );
  });

  it('falls back to JSON.stringify when any element lacks a {msg: string} shape', () => {
    const detail = [
      { msg: 'good msg' },
      { weird: 'no msg key here' },
    ];
    expect(flattenErrorDetail(detail)).toBe(JSON.stringify(detail));
  });

  it('returns undefined for empty arrays', () => {
    expect(flattenErrorDetail([])).toBeUndefined();
  });

  it('JSON-stringifies object detail (legacy / custom raisers)', () => {
    expect(flattenErrorDetail({ code: 'X', hint: 'Y' })).toBe('{"code":"X","hint":"Y"}');
  });

  it('returns undefined for null / undefined', () => {
    expect(flattenErrorDetail(null)).toBeUndefined();
    expect(flattenErrorDetail(undefined)).toBeUndefined();
  });
});

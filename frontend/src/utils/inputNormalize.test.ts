import { describe, it, expect } from 'vitest';
import { normalizePhone, normalizeEmail, clampNumberInput } from './inputNormalize';

describe('normalizePhone', () => {
  it('strips parentheses, dashes, and spaces', () => {
    expect(normalizePhone('(555) 123-4567')).toBe('5551234567');
  });

  it('preserves a single leading plus and collapses repeats', () => {
    expect(normalizePhone('+1 (555) 123-4567')).toBe('+15551234567');
    expect(normalizePhone('++1 555')).toBe('+1555');
  });
});

describe('normalizeEmail', () => {
  it('trims trailing whitespace and lowercases', () => {
    expect(normalizeEmail('John@EXAMPLE.COM ')).toBe('john@example.com');
  });
});

describe('clampNumberInput', () => {
  it('rejects non-numeric characters and falls back to 0', () => {
    expect(clampNumberInput('ABC')).toBe('0');
  });

  it('clamps to max', () => {
    expect(clampNumberInput('150', { min: 0, max: 100 })).toBe('100');
  });

  it('strips negatives when min >= 0', () => {
    expect(clampNumberInput('-5', { min: 0 })).toBe('5');
  });

  it('keeps a single decimal point', () => {
    expect(clampNumberInput('1.2.3', { allowDecimal: true })).toBe('1.23');
  });
});

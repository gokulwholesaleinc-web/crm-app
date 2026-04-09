import { describe, it, expect } from 'vitest';
import { sanitizeHexColor, isValidHexColor } from './colorValidation';

describe('sanitizeHexColor', () => {
  const FALLBACK = '#6366f1';

  it('accepts 6-digit hex', () => {
    expect(sanitizeHexColor('#ff00aa', FALLBACK)).toBe('#ff00aa');
    expect(sanitizeHexColor('#FFAA00', FALLBACK)).toBe('#FFAA00');
  });

  it('accepts 3-digit shorthand', () => {
    expect(sanitizeHexColor('#fa0', FALLBACK)).toBe('#fa0');
    expect(sanitizeHexColor('#ABC', FALLBACK)).toBe('#ABC');
  });

  it('accepts 8-digit hex with alpha', () => {
    expect(sanitizeHexColor('#ff00aa80', FALLBACK)).toBe('#ff00aa80');
  });

  it('trims whitespace before checking', () => {
    expect(sanitizeHexColor('  #ff00aa  ', FALLBACK)).toBe('#ff00aa');
  });

  it('rejects missing hash', () => {
    expect(sanitizeHexColor('ff00aa', FALLBACK)).toBe(FALLBACK);
  });

  it('rejects non-hex characters', () => {
    expect(sanitizeHexColor('#ggg000', FALLBACK)).toBe(FALLBACK);
    expect(sanitizeHexColor('#zzz', FALLBACK)).toBe(FALLBACK);
  });

  it('rejects wrong length', () => {
    expect(sanitizeHexColor('#ff00a', FALLBACK)).toBe(FALLBACK); // 5
    expect(sanitizeHexColor('#ff00aab', FALLBACK)).toBe(FALLBACK); // 7
    expect(sanitizeHexColor('#ff00aab0b', FALLBACK)).toBe(FALLBACK); // 9
  });

  it('rejects CSS expressions / injection attempts', () => {
    // The historical concern: if a server returns a malformed color string,
    // React escapes style values but echoing an attacker-controlled string
    // into `style={{ backgroundColor: ... }}` is still risky. This test
    // documents that anything that isn't a strict hex gets dropped.
    expect(sanitizeHexColor('red; background: url(javascript:alert(1))', FALLBACK)).toBe(FALLBACK);
    expect(sanitizeHexColor('rgb(255, 0, 0)', FALLBACK)).toBe(FALLBACK);
    expect(sanitizeHexColor('red', FALLBACK)).toBe(FALLBACK);
    expect(sanitizeHexColor('var(--color-primary)', FALLBACK)).toBe(FALLBACK);
    expect(sanitizeHexColor('</style><script>alert(1)</script>', FALLBACK)).toBe(FALLBACK);
  });

  it('rejects null/undefined/non-string', () => {
    expect(sanitizeHexColor(null, FALLBACK)).toBe(FALLBACK);
    expect(sanitizeHexColor(undefined, FALLBACK)).toBe(FALLBACK);
    expect(sanitizeHexColor('', FALLBACK)).toBe(FALLBACK);
  });
});

describe('isValidHexColor', () => {
  it('matches sanitizeHexColor acceptance criteria', () => {
    expect(isValidHexColor('#ff00aa')).toBe(true);
    expect(isValidHexColor('#fa0')).toBe(true);
    expect(isValidHexColor('#ff00aa80')).toBe(true);
    expect(isValidHexColor('ff00aa')).toBe(false);
    expect(isValidHexColor('red')).toBe(false);
    expect(isValidHexColor(null)).toBe(false);
    expect(isValidHexColor(undefined)).toBe(false);
  });
});

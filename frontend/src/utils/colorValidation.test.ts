import { describe, it, expect } from 'vitest';
import { sanitizeHexColor, isValidHexColor, withAlpha } from './colorValidation';

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

describe('withAlpha', () => {
  it('appends alpha to a 6-digit hex unchanged', () => {
    expect(withAlpha('#64f28f', '14')).toBe('#64f28f14');
  });

  it('expands 3-digit shorthand to 6 before appending alpha', () => {
    expect(withAlpha('#fa0', '40')).toBe('#ffaa0040');
    expect(withAlpha('#ABC', '0f')).toBe('#AABBCC0f');
  });

  it('strips existing alpha from 8-digit hex before appending', () => {
    expect(withAlpha('#64f28fff', '14')).toBe('#64f28f14');
  });

  it('returns transparent for invalid input rather than producing broken CSS', () => {
    expect(withAlpha('not-a-color', '14')).toBe('transparent');
    expect(withAlpha('rgb(0,0,0)', '14')).toBe('transparent');
    expect(withAlpha('', '14')).toBe('transparent');
    expect(withAlpha('#ff00a', '14')).toBe('transparent');
  });

  it('trims whitespace before validating', () => {
    expect(withAlpha('  #64f28f  ', '14')).toBe('#64f28f14');
  });
});

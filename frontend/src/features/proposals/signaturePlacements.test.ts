import { describe, expect, it } from 'vitest';
import type { SignatureFieldCoordsValue } from '../../types';
import {
  formatSignaturePlacementSummary,
  hasSignaturePlacements,
  normalizeSignaturePlacements,
} from './signaturePlacements';

describe('signature placement helpers', () => {
  it('filters malformed saved placements instead of counting invisible boxes', () => {
    const value = [
      { page: 2, x: 10, y: 20, w: 100, h: 40 },
      { page: 1, x: Number.NaN, y: 20, w: 100, h: 40 },
      { page: 1, x: 20, y: 20, w: 0, h: 40 },
      { page: '1', x: 20, y: 20, w: 100, h: 40 },
    ] as unknown as SignatureFieldCoordsValue;

    expect(normalizeSignaturePlacements(value)).toEqual([
      { page: 2, x: 10, y: 20, w: 100, h: 40 },
    ]);
    expect(hasSignaturePlacements(value)).toBe(true);
    expect(
      formatSignaturePlacementSummary(value, 'signature', 'signatures'),
    ).toBe('1 signature on page 2');
  });

  it('treats entirely malformed values as missing', () => {
    expect(
      hasSignaturePlacements({ page: 1, x: 10, y: 20, w: 0, h: 40 } as never),
    ).toBe(false);
    expect(
      hasSignaturePlacements([{ page: 1, x: 10, y: 20, w: 0, h: 40 }] as never),
    ).toBe(false);
    expect(normalizeSignaturePlacements(null)).toEqual([]);
  });
});

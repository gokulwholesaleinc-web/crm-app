/**
 * Round-trip property for the shared PDF coordinate math used by the
 * onboarding editor: drawing a box → PDF points → back to a box must be the
 * identity (within float tolerance). A regression here silently shifts every
 * placed field, so it is pinned independently of the editor component.
 */
import { describe, it, expect } from 'vitest';
import { boxToPdfCoords, pdfCoordsToBox, type DrawnBox } from '../../lib/pdfCoords';

const CANVAS_H = 792 * 1.5; // a US-Letter page rendered at RENDER_SCALE.

const SAMPLES: DrawnBox[] = [
  { pageIdx: 0, leftPx: 0, topPx: 0, widthPx: 150, heightPx: 45 },
  { pageIdx: 0, leftPx: 120.5, topPx: 240.25, widthPx: 200, heightPx: 60 },
  { pageIdx: 2, leftPx: 480, topPx: 1000, widthPx: 90, heightPx: 30 },
  { pageIdx: 1, leftPx: 33.3, topPx: 700.7, widthPx: 11.1, heightPx: 88.8 },
];

describe('pdfCoords — boxToPdfCoords ∘ pdfCoordsToBox is identity', () => {
  it.each(SAMPLES)('round-trips %o', (box) => {
    const pdf = boxToPdfCoords(box, CANVAS_H);
    const back = pdfCoordsToBox({ page: box.pageIdx + 1, ...pdf }, CANVAS_H);

    expect(back.pageIdx).toBe(box.pageIdx);
    expect(back.leftPx).toBeCloseTo(box.leftPx, 6);
    expect(back.topPx).toBeCloseTo(box.topPx, 6);
    expect(back.widthPx).toBeCloseTo(box.widthPx, 6);
    expect(back.heightPx).toBeCloseTo(box.heightPx, 6);
  });

  it('keeps PDF y as the bottom edge (origin bottom-left)', () => {
    // A box 45px tall whose top is at y=0 sits flush against the page top;
    // its PDF bottom edge must be (pageHeight - boxHeight) in points.
    const pdf = boxToPdfCoords(
      { pageIdx: 0, leftPx: 0, topPx: 0, widthPx: 150, heightPx: 45 },
      CANVAS_H,
    );
    expect(pdf.y).toBeCloseTo(792 - 45 / 1.5, 6);
  });
});

/**
 * Kind-agnostic PDF coordinate math shared by the proposals signature-field
 * picker and the onboarding template editor.
 *
 * Both editors render a PDF page to a canvas at {@link RENDER_SCALE} and let
 * the user drag a box on top of it. The screen-pixel box has to be converted
 * to PDF points (origin bottom-left) for storage, and back again to pre-fill
 * the canvas with a saved box. That conversion is identical regardless of
 * what *kind* of field is being placed, so it lives here — neutral, with no
 * dependency on either feature's field-kind type.
 *
 * This module was extracted from ``features/proposals/SignatureFieldPicker``
 * verbatim (same constant, same arithmetic) — do not change the math without
 * re-verifying both editors round-trip identically.
 */

/**
 * Scale factor used to render each PDF page to its canvas. 1 PDF point
 * (1/72 in) renders to ``RENDER_SCALE`` device-independent pixels.
 */
export const RENDER_SCALE = 1.5;

/** A box drawn on a pdf.js-rendered canvas, in screen pixels. */
export interface DrawnBox {
  /** Page index in pdf.js space (0-indexed). */
  pageIdx: number;
  /** Screen-pixel box relative to the rendered canvas. */
  leftPx: number;
  topPx: number;
  widthPx: number;
  heightPx: number;
}

/** PDF-point box (origin bottom-left). Page is tracked separately. */
export interface PdfBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export function clamp(value: number, min: number, max: number): number {
  if (value < min) return min;
  if (value > max) return max;
  return value;
}

/**
 * Convert a screen-pixel box on a pdf.js-rendered canvas to PDF points.
 *
 * pdf.js renders top-down; PDF points are bottom-up, so the y axis
 * flips and the saved ``y`` is the **bottom** edge of the box. The
 * canvas was rendered at ``RENDER_SCALE``, so dividing through gives
 * us back PDF points (1 pt = 1/72 in).
 */
export function boxToPdfCoords(box: DrawnBox, canvasHeightPx: number): PdfBox {
  const x = box.leftPx / RENDER_SCALE;
  const w = box.widthPx / RENDER_SCALE;
  const h = box.heightPx / RENDER_SCALE;
  const bottomPx = box.topPx + box.heightPx;
  const y = (canvasHeightPx - bottomPx) / RENDER_SCALE;
  return { x, y, w, h };
}

/** Inverse of {@link boxToPdfCoords}. Pre-fills the canvas with the saved box. */
export function pdfCoordsToBox(
  coords: { page: number } & PdfBox,
  canvasHeightPx: number,
): DrawnBox {
  const widthPx = coords.w * RENDER_SCALE;
  const heightPx = coords.h * RENDER_SCALE;
  const leftPx = coords.x * RENDER_SCALE;
  const bottomPx = canvasHeightPx - coords.y * RENDER_SCALE;
  const topPx = bottomPx - heightPx;
  return {
    pageIdx: coords.page - 1,
    leftPx,
    topPx,
    widthPx,
    heightPx,
  };
}

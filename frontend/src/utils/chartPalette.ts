/**
 * Chart palette resolved against tenant branding CSS vars at render time.
 * Series 1-3 follow the admin-configured brand colors so secondary/accent
 * are visible in charts; series 4+ use a fixed neutral tail.
 */

import { isValidHexColor } from './colorValidation';

const FALLBACK_TAIL = [
  '#06b6d4',
  '#84cc16',
  '#f97316',
  '#6366f1',
  '#ec4899',
  '#8b5cf6',
  '#f59e0b',
  '#ef4444',
  '#10b981',
  '#3b82f6',
];

type BrandToken = 'primary' | 'secondary' | 'accent';

function readBrandVar(token: BrandToken): string | null {
  if (typeof document === 'undefined') return null;
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(`--brand-${token}`)
    .trim();
  return isValidHexColor(raw) ? raw : null;
}

export function getBrandColor(token: BrandToken, fallback: string): string {
  return readBrandVar(token) ?? fallback;
}

export function getChartPalette(): string[] {
  if (typeof document === 'undefined') return [...FALLBACK_TAIL];

  const head: string[] = [];
  for (const token of ['primary', 'secondary', 'accent'] as const) {
    const hex = readBrandVar(token);
    if (hex) head.push(hex);
  }
  return [...head, ...FALLBACK_TAIL];
}

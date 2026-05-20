import type { SignatureFieldCoords, SignatureFieldCoordsValue } from '../../types';

export function normalizeSignaturePlacements(
  value: SignatureFieldCoordsValue | null | undefined,
): SignatureFieldCoords[] {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

export function hasSignaturePlacements(
  value: SignatureFieldCoordsValue | null | undefined,
): boolean {
  return normalizeSignaturePlacements(value).length > 0;
}

export function formatSignaturePlacementSummary(
  value: SignatureFieldCoordsValue | null | undefined,
  singularLabel: string,
  pluralLabel: string,
): string {
  const placements = normalizeSignaturePlacements(value);
  if (placements.length === 0) return `no ${pluralLabel}`;
  const pages = Array.from(new Set(placements.map((placement) => placement.page)))
    .sort((a, b) => a - b)
    .join(', ');
  return `${placements.length} ${placements.length === 1 ? singularLabel : pluralLabel} on page${
    pages.includes(',') ? 's' : ''
  } ${pages}`;
}

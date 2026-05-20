import type {
  SignatureFieldCoords,
  SignatureFieldCoordsValue,
} from '../../types/proposals';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

// Keep in sync with backend/src/proposals/schemas.py::SignatureFieldCoords.
export function isSignatureFieldCoords(
  value: unknown,
): value is SignatureFieldCoords {
  if (!isRecord(value)) return false;
  const { page, x, y, w, h } = value;
  return (
    typeof page === 'number' &&
    Number.isInteger(page) &&
    page >= 1 &&
    typeof x === 'number' &&
    Number.isFinite(x) &&
    x >= 0 &&
    typeof y === 'number' &&
    Number.isFinite(y) &&
    y >= 0 &&
    typeof w === 'number' &&
    Number.isFinite(w) &&
    w > 0 &&
    typeof h === 'number' &&
    Number.isFinite(h) &&
    h > 0
  );
}

export function normalizeSignaturePlacements(
  value: SignatureFieldCoordsValue | null | undefined,
): SignatureFieldCoords[] {
  if (!value) return [];
  return Array.isArray(value)
    ? value.filter(isSignatureFieldCoords)
    : isSignatureFieldCoords(value)
      ? [value]
      : [];
}

export function hasSignaturePlacements(
  value: SignatureFieldCoordsValue | null | undefined,
): boolean {
  if (!value) return false;
  return Array.isArray(value)
    ? value.length > 0 && value.every(isSignatureFieldCoords)
    : isSignatureFieldCoords(value);
}

export function hasInvalidSignaturePlacements(
  value: SignatureFieldCoordsValue | null | undefined,
): boolean {
  if (!value) return false;
  return Array.isArray(value)
    ? value.length > 0 && !value.every(isSignatureFieldCoords)
    : !isSignatureFieldCoords(value);
}

export function formatSignaturePlacementSummary(
  value: SignatureFieldCoordsValue | null | undefined,
  singularLabel: string,
  pluralLabel: string,
): string {
  if (hasInvalidSignaturePlacements(value)) return `invalid ${pluralLabel}`;
  const placements = normalizeSignaturePlacements(value);
  if (placements.length === 0) return `no ${pluralLabel}`;
  const pages = Array.from(
    new Set(placements.map((placement) => placement.page)),
  )
    .sort((a, b) => a - b)
    .join(', ');
  return `${placements.length} ${placements.length === 1 ? singularLabel : pluralLabel} on page${
    pages.includes(',') ? 's' : ''
  } ${pages}`;
}

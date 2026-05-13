/**
 * Parse a possibly-formatted number string ("1,000,000", "$ 5000") into an int.
 *
 * Returns null when nothing parseable remains so the field can clear.
 * Critical: a naive parseInt("1,000,000", 10) returns 1 — silent 6-zero
 * data loss for revenue / employee_count. This strip-and-parse keeps
 * user-typed commas / currency intact in the UX while persisting the
 * right integer.
 */
export function parseLooseInt(value: string): number | null {
  if (!value) return null;
  const stripped = value.replace(/[^\d-]/g, '');
  if (!stripped || stripped === '-') return null;
  const n = Number(stripped);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

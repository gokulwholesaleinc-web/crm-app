/**
 * Parse a possibly-formatted number string ("1,000,000", "$ 5000", "1.5M
 * → no, only the digits part) into an int.
 *
 * Returns null when nothing parseable remains so the field can clear.
 *
 * Critical: the obvious `parseInt("1,000,000", 10)` returns 1 (silent
 * 6-zero data loss). The next obvious fix — `value.replace(/[^\d-]/g,
 * '')` — strips the decimal point too, so "100.99" round-trips as 10099
 * (a 100× inflation on revenue). Keep the `.` and `-` in the strip
 * regex, then Number() + Math.trunc() to drop the fractional part.
 */
export function parseLooseInt(value: string): number | null {
  if (!value) return null;
  const stripped = value.replace(/[^\d.-]/g, '');
  if (!stripped || stripped === '-' || stripped === '.') return null;
  const n = Number(stripped);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

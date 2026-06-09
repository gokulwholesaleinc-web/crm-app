/**
 * Date-range presets for the reporting workspace (7D / 14D / 30D / 90D / All +
 * custom). Pure date math in UTC so the URL state is deterministic and the
 * window is unambiguous; the server re-buckets in the client's reporting tz (A8).
 */

export type RangePreset = '7d' | '14d' | '30d' | '90d' | 'all' | 'custom';

export interface DateRange {
  date_from: string; // YYYY-MM-DD
  date_to: string;
}

export const PRESET_LABELS: Record<Exclude<RangePreset, 'custom'>, string> = {
  '7d': '7D',
  '14d': '14D',
  '30d': '30D',
  '90d': '90D',
  all: 'All',
};

const PRESET_DAYS: Record<'7d' | '14d' | '30d' | '90d', number> = {
  '7d': 7,
  '14d': 14,
  '30d': 30,
  '90d': 90,
};

// ~13 months — the warehouse retention target so "All" yields YoY-capable data.
const ALL_DAYS = 400;

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function shiftDays(from: Date, days: number): Date {
  const d = new Date(from);
  d.setUTCDate(d.getUTCDate() - days);
  return d;
}

/** Resolve a preset to an inclusive [date_from, date_to] ending today. */
export function presetRange(preset: Exclude<RangePreset, 'custom'>, today: Date = new Date()): DateRange {
  const end = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()));
  const span = preset === 'all' ? ALL_DAYS : PRESET_DAYS[preset];
  return { date_from: iso(shiftDays(end, span - 1)), date_to: iso(end) };
}

/** The prior equal-length window immediately preceding `range` (for delta labels). */
export function compareRange(range: DateRange): DateRange {
  const from = new Date(`${range.date_from}T00:00:00Z`);
  const to = new Date(`${range.date_to}T00:00:00Z`);
  const spanDays = Math.round((to.getTime() - from.getTime()) / 86_400_000);
  const compareTo = shiftDays(from, 1);
  const compareFrom = shiftDays(compareTo, spanDays);
  return { date_from: iso(compareFrom), date_to: iso(compareTo) };
}

export function isValidPreset(value: string | null): value is RangePreset {
  return value === '7d' || value === '14d' || value === '30d' || value === '90d' || value === 'all' || value === 'custom';
}

/**
 * Locale-aware formatters for the marketing reporting surface.
 *
 * Every number/date the dashboard shows goes through one of these — never a
 * hand-rolled `toFixed` or `${n}%` (CLAUDE.md web-interface rules). Formatter
 * instances are hoisted to module scope and memoized per (locale, currency) so
 * we don't allocate an `Intl.NumberFormat` on every render.
 *
 * Critical contract: `formatPercent` takes a RATIO (0.15 → "15%"), matching the
 * server, which stores ratios not pre-multiplied percentages. Null/undefined →
 * an em-dash ("—"), never "NaN%"/"Infinity%" — the divide-by-zero values the
 * aggregation layer returns as `null` (A5).
 */

const EM_DASH = '—';

const _currencyFmts = new Map<string, Intl.NumberFormat>();
const _compactCurrencyFmts = new Map<string, Intl.NumberFormat>();

function currencyFmt(currency: string, compact: boolean): Intl.NumberFormat {
  const cache = compact ? _compactCurrencyFmts : _currencyFmts;
  let fmt = cache.get(currency);
  if (!fmt) {
    fmt = new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      ...(compact
        ? { notation: 'compact', maximumFractionDigits: 1 }
        : { maximumFractionDigits: 2 }),
    });
    cache.set(currency, fmt);
  }
  return fmt;
}

const _percentFmt = new Intl.NumberFormat(undefined, {
  style: 'percent',
  maximumFractionDigits: 1,
  signDisplay: 'never',
});
const _signedPercentFmt = new Intl.NumberFormat(undefined, {
  style: 'percent',
  maximumFractionDigits: 1,
  signDisplay: 'exceptZero',
});
const _numberFmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
const _compactNumberFmt = new Intl.NumberFormat(undefined, {
  notation: 'compact',
  maximumFractionDigits: 1,
});
const _decimalFmt = new Intl.NumberFormat(undefined, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

type Numish = number | string | null | undefined;

/** Coerce server Decimals (which arrive as strings over JSON) to a number. */
function toNum(value: Numish): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = typeof value === 'string' ? Number(value) : value;
  return Number.isFinite(n) ? n : null;
}

/** Money. `compact` (e.g. "$1.2K") for KPI cards; full precision in tables. */
export function formatCurrency(value: Numish, currency = 'USD', compact = false): string {
  const n = toNum(value);
  if (n === null) return EM_DASH;
  return currencyFmt(currency, compact).format(n);
}

/** A ratio (0.15) → "15%". Null (÷0) → em-dash. */
export function formatPercent(ratio: Numish): string {
  const n = toNum(ratio);
  if (n === null) return EM_DASH;
  return _percentFmt.format(n);
}

/** A ratio with an explicit +/- sign, for delta chips. */
export function formatSignedPercent(ratio: Numish): string {
  const n = toNum(ratio);
  if (n === null) return EM_DASH;
  return _signedPercentFmt.format(n);
}

/** Whole-number counts (impressions, clicks). `compact` for cards. */
export function formatNumber(value: Numish, compact = false): string {
  const n = toNum(value);
  if (n === null) return EM_DASH;
  return (compact ? _compactNumberFmt : _numberFmt).format(n);
}

/** Two-decimal values (ROAS, CPC shown as a ratio not currency). */
export function formatDecimal(value: Numish): string {
  const n = toNum(value);
  if (n === null) return EM_DASH;
  return _decimalFmt.format(n);
}

// timeZone: 'UTC' is load-bearing (C3): a date-only ISO string like "2026-06-01"
// is parsed by `new Date(...)` as UTC midnight; formatting in the viewer's local
// zone would render "May 31" for any negative-UTC-offset user (e.g. the app's own
// America/Chicago reporting tz), shifting every trend/table date back a day. Pinning
// the formatter to UTC keeps the rendered day equal to the stored calendar date.
const _dateFmt = new Intl.DateTimeFormat(undefined, {
  month: 'short',
  day: 'numeric',
  timeZone: 'UTC',
});
const _dateYearFmt = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  timeZone: 'UTC',
});

/** "Jun 8" (or "Jun 8, 2026" with year). Accepts an ISO date string or Date. */
export function formatDate(value: string | Date | null | undefined, withYear = false): string {
  if (!value) return EM_DASH;
  const d = typeof value === 'string' ? new Date(value) : value;
  if (Number.isNaN(d.getTime())) return EM_DASH;
  return (withYear ? _dateYearFmt : _dateFmt).format(d);
}

/** Relative freshness: "just now" / "5m ago" / "3h ago" / "2d ago". For the
 *  truthful "Updated …" data-trust signal, sourced from real last-sync time. */
export function formatRelativeTime(
  value: string | Date | null | undefined,
  now: Date = new Date(),
): string {
  if (!value) return 'never';
  const then = typeof value === 'string' ? new Date(value) : value;
  if (Number.isNaN(then.getTime())) return 'never';
  const secs = Math.round((now.getTime() - then.getTime()) / 1000);
  if (secs < 60) return 'just now';
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

export { EM_DASH };

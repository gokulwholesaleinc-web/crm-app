/**
 * Shared proposal billing formatters.
 *
 * Used by the public proposal page and the CRM billing sidebar card
 * so both surfaces speak the same language for payment cadence and
 * amount formatting. The two money variants differ only in fallback
 * (`'—'` for CRM tables vs `null` for the document view pull-figure)
 * and in fraction digits (forced 2 for the public view to always show
 * cents on receipts; currency-default for the CRM card).
 */

export const CADENCE_LABELS: Record<string, string> = {
  'month-1': 'Monthly',
  'month-3': 'Quarterly',
  'month-6': 'Bi-yearly',
  'year-1': 'Yearly',
};

export function cadenceLabel(
  interval: string | null | undefined,
  count: number | null | undefined,
): string {
  if (!interval) return '';
  const normalized = count ?? 1;
  const key = `${interval}-${normalized}`;
  if (CADENCE_LABELS[key]) return CADENCE_LABELS[key];
  const plural = normalized > 1 ? 's' : '';
  return `Every ${normalized} ${interval}${plural}`;
}

function parseAmount(amount: string | number | null | undefined): number | null {
  if (amount == null || amount === '') return null;
  const num = typeof amount === 'string' ? Number(amount) : amount;
  return Number.isFinite(num) ? num : null;
}

/**
 * Returns `null` for missing/invalid amounts. Forces 2 fraction digits
 * so the public document always shows cents on the pull-figure.
 */
export function formatProposalMoney(
  amount: string | number | null | undefined,
  currency: string,
): string | null {
  const num = parseAmount(amount);
  if (num === null) return null;
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
    }).format(num);
  } catch {
    return `${currency} ${num.toFixed(2)}`;
  }
}

/**
 * Returns `'—'` for missing/invalid amounts. Uses the currency's own
 * default fraction digits (e.g. JPY → 0), matching the original CRM
 * billing card behavior.
 */
export function formatProposalMoneyOrDash(
  amount: string | number | null | undefined,
  currency: string,
): string {
  const num = parseAmount(amount);
  if (num === null) return '—';
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(num);
  } catch {
    return `${currency} ${num.toFixed(2)}`;
  }
}

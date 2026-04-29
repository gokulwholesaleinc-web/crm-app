// Shared proposal billing formatters used by both the CRM billing card
// and the public proposal page. Two money variants exist because their
// fallbacks differ ('—' vs null) and the public view forces 2 fraction
// digits to always show cents on the pull-figure.

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

function formatMoney<F>(
  amount: string | number | null | undefined,
  currency: string,
  fallback: F,
  options?: Intl.NumberFormatOptions,
): string | F {
  const num = parseAmount(amount);
  if (num === null) return fallback;
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, ...options }).format(num);
  } catch {
    return `${currency} ${num.toFixed(2)}`;
  }
}

export function formatProposalMoney(
  amount: string | number | null | undefined,
  currency: string,
): string | null {
  return formatMoney(amount, currency, null, { minimumFractionDigits: 2 });
}

export function formatProposalMoneyOrDash(
  amount: string | number | null | undefined,
  currency: string,
): string {
  return formatMoney(amount, currency, '—');
}

/**
 * Map a server MetricCard → KpiCard display props. The server hands a percentage
 * (20.0) and a per-metric `is_good`; the card wants a ratio (0.2) and a sentiment.
 */

import type { MetricCard } from '../../../api/marketing';
import type { KpiDelta } from '../components/KpiCard';
import { formatCurrency, formatDecimal, formatNumber, formatPercent } from './format';

export function formatCardValue(card: MetricCard, currency: string): string {
  switch (card.format) {
    case 'currency':
      return formatCurrency(card.value, currency);
    case 'percent':
      return formatPercent(card.value);
    case 'ratio':
      return formatDecimal(card.value);
    default:
      return formatNumber(card.value);
  }
}

export function toKpiDelta(card: MetricCard): KpiDelta | null {
  const d = card.delta;
  if (!d) return null;
  return {
    pct: d.pct === null ? null : d.pct / 100, // server percent (20.0) → ratio (0.2)
    sentiment: d.is_good === true ? 'good' : d.is_good === false ? 'bad' : 'neutral',
    isNew: d.is_new,
  };
}

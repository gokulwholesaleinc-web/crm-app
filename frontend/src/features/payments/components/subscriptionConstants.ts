import type { RecurringInterval } from '../../../types/proposals';

export const INTERVAL_PRESETS: Array<{ label: string; interval: RecurringInterval; count: number }> = [
  { label: 'Monthly', interval: 'month', count: 1 },
  { label: 'Quarterly', interval: 'month', count: 3 },
  { label: 'Bi-yearly', interval: 'month', count: 6 },
  { label: 'Yearly', interval: 'year', count: 1 },
];

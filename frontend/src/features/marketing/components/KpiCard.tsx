import clsx from 'clsx';
import { Card, Skeleton } from '../../../components/ui';
import { formatSignedPercent } from '../utils/format';

/**
 * A period-over-period delta, computed SERVER-side (A6): the sign lives in `pct`
 * (a signed ratio, +0.2 = +20%), but whether that move is *good* is per-metric
 * (CPC down is good) so the server hands us `sentiment` rather than us inferring
 * it from the sign. `isNew` means there was no comparable prior period (a
 * zero-baseline) — shown as "New", never as a fake "+100%".
 */
export interface KpiDelta {
  pct: number | null;
  sentiment: 'good' | 'bad' | 'neutral';
  isNew: boolean;
}

export interface KpiCardProps {
  label: string;
  /** Pre-formatted display value (caller uses the Intl helpers). */
  value: string;
  delta?: KpiDelta | null;
  /** e.g. "vs prior 30 days" — the compare window, disclosed not implied. */
  timeframe?: string;
  /** Optional data-trust line: source · timezone · attribution window. */
  hint?: string;
  isLoading?: boolean;
}

const sentimentText: Record<KpiDelta['sentiment'], string> = {
  good: 'text-green-700 dark:text-green-400',
  bad: 'text-red-700 dark:text-red-400',
  neutral: 'text-gray-500 dark:text-gray-400',
};

function DeltaChip({ delta }: { delta: KpiDelta }) {
  if (delta.isNew) {
    return (
      <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-300">
        New
      </span>
    );
  }
  if (delta.pct === null) {
    return (
      <span className="text-xs text-gray-400" aria-label="no change data">
        —
      </span>
    );
  }
  const dir = delta.pct > 0 ? 'up' : delta.pct < 0 ? 'down' : 'unchanged';
  const arrow = dir === 'up' ? '▲' : dir === 'down' ? '▼' : '–';
  return (
    <span className={clsx('inline-flex items-center gap-1 text-xs font-medium tabular-nums', sentimentText[delta.sentiment])}>
      {/* Arrow + sign + number together — direction is never conveyed by color alone (WCAG 1.4.1). */}
      <span aria-hidden="true">{arrow}</span>
      <span>{formatSignedPercent(delta.pct)}</span>
      <span className="sr-only">{`${dir} versus the previous period`}</span>
    </span>
  );
}

/**
 * One KPI card: Label → Value → Delta → Timeframe (CLAUDE.md card anatomy).
 * Value column uses `tabular-nums` so figures align across the grid.
 */
export function KpiCard({ label, value, delta, timeframe, hint, isLoading }: KpiCardProps) {
  return (
    <Card padding="md" className="min-w-0">
      <div className="flex flex-col gap-1">
        <span className="truncate text-sm font-medium text-gray-500 dark:text-gray-400">{label}</span>
        {isLoading ? (
          <Skeleton className="h-8 w-24" />
        ) : (
          <span className="text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-100">
            {value}
          </span>
        )}
        <div className="flex items-center gap-2">
          {!isLoading && delta && <DeltaChip delta={delta} />}
          {timeframe && <span className="truncate text-xs text-gray-400">{timeframe}</span>}
        </div>
        {hint && <span className="truncate text-xs text-gray-400" title={hint}>{hint}</span>}
      </div>
    </Card>
  );
}

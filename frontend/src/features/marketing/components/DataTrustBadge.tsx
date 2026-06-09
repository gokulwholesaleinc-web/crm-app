import clsx from 'clsx';
import { formatRelativeTime } from '../utils/format';

export type ConnectionHealth = 'active' | 'needs_reauth' | 'error' | 'pending' | 'disabled';

export interface SourceFreshness {
  /** Human label: "GA4", "Google Ads", "Search Console". */
  source: string;
  lastSyncedAt: string | null;
  status: ConnectionHealth;
}

export interface DataTrustBadgeProps {
  sources: SourceFreshness[];
  /** The single reporting timezone all buckets/deltas use (A8) — disclosed. */
  timezone?: string;
  className?: string;
}

const dotByStatus: Record<ConnectionHealth, string> = {
  active: 'bg-green-500',
  pending: 'bg-gray-400',
  needs_reauth: 'bg-amber-500',
  error: 'bg-red-500',
  disabled: 'bg-gray-300',
};

function label(s: SourceFreshness): string {
  switch (s.status) {
    case 'needs_reauth':
      return 'Reconnect needed';
    case 'error':
      return 'Sync error';
    case 'pending':
      return 'Not yet synced';
    case 'disabled':
      return 'Disabled';
    default:
      return `Updated ${formatRelativeTime(s.lastSyncedAt)}`;
  }
}

/**
 * Truthful per-source freshness — sourced from the real last successful ingest,
 * not page load (§5). An expired token reads as "Reconnect needed", never a
 * silent zero. The reporting timezone is disclosed so numbers aren't mistaken
 * for the viewer's local day.
 */
export function DataTrustBadge({ sources, timezone, className }: DataTrustBadgeProps) {
  return (
    <div
      className={clsx('flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400', className)}
      aria-live="polite"
    >
      {sources.map((s) => (
        <span key={s.source} className="inline-flex items-center gap-1.5">
          <span
            className={clsx('inline-block h-2 w-2 shrink-0 rounded-full', dotByStatus[s.status])}
            aria-hidden="true"
          />
          <span className="font-medium text-gray-600 dark:text-gray-300">{s.source}</span>
          <span>· {label(s)}</span>
        </span>
      ))}
      {timezone && <span className="text-gray-400">All times {timezone}</span>}
    </div>
  );
}

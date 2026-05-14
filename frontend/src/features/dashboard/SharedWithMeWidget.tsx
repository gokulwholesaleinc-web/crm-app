/**
 * SharedWithMeWidget — shows records shared with the current user,
 * grouped by entity_type, up to 5 per type.
 */

import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '../../store/authStore';
import { fetchSharedWithMe } from '../../api/me';
import type { SharedWithMeItem } from '../../api/me';
import { ChartCard } from './components/ChartCard';

// ---------------------------------------------------------------------------
// Relative timestamp helper
// ---------------------------------------------------------------------------

function relativeTime(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return 'just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

// ---------------------------------------------------------------------------
// Entity-type display config
// ---------------------------------------------------------------------------

// ``quotes`` retired 2026-05-14 — quotes router unmounted. Historical
// EntityShare rows with ``entity_type='quotes'`` no longer surface here
// (the API path that powers this widget skips legacy types).
const ENTITY_LABELS: Record<string, string> = {
  leads: 'Leads',
  contracts: 'Contracts',
  proposals: 'Proposals',
  campaigns: 'Campaigns',
  contacts: 'Contacts',
  companies: 'Companies',
};

// Simple SVG path icons keyed by entity_type
function EntityIcon({ entityType }: { entityType: string }) {
  const icons: Record<string, string> = {
    leads:
      'M13 7h8m0 0v8m0-8l-8 8-4-4-6 6',
    contracts:
      'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
    proposals:
      'M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z',
    campaigns:
      'M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z',
    contacts:
      'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z',
    companies:
      'M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4',
  };
  const d = icons[entityType] ?? 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z';
  return (
    <svg
      className="h-4 w-4 text-primary-500 dark:text-primary-400 flex-shrink-0"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      aria-hidden="true"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={d} />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Row component
// ---------------------------------------------------------------------------

function SharedItemRow({ item }: { item: SharedWithMeItem }) {
  const href = `/${item.entity_type}/${item.entity_id}`;
  return (
    <li>
      <Link
        to={href}
        className="flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-gray-700/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors"
      >
        <span className="mt-0.5">
          <EntityIcon entityType={item.entity_type} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
            {item.title}
          </span>
          <span className="block text-xs text-gray-500 dark:text-gray-400 truncate">
            {item.owner_name ? `Owned by ${item.owner_name}` : 'No owner'}{' '}
            &middot; {relativeTime(item.shared_at)}
          </span>
        </span>
      </Link>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Widget
// ---------------------------------------------------------------------------

export function SharedWithMeWidget() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const authLoading = useAuthStore((s) => s.isLoading);

  const { data, isLoading } = useQuery({
    queryKey: ['me', 'shared'],
    queryFn: fetchSharedWithMe,
    staleTime: 60 * 1000,
    enabled: isAuthenticated && !authLoading,
  });

  // Hide entirely while loading or when there are no shares
  if (isLoading || !data || data.total === 0) {
    return null;
  }

  const entityTypes = Object.keys(data.items_by_type);

  return (
    <ChartCard
      title="Shared with me"
      subtitle={`${data.total} record${data.total === 1 ? '' : 's'} shared with you`}
    >
      <div className="space-y-4">
        {entityTypes.map((entityType) => {
          const items = data.items_by_type[entityType];
          if (!items || items.length === 0) return null;
          return (
            <div key={entityType}>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                {ENTITY_LABELS[entityType] ?? entityType}
              </h4>
              <ul className="space-y-0.5">
                {items.map((item) => (
                  <SharedItemRow key={`${item.entity_type}-${item.entity_id}`} item={item} />
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </ChartCard>
  );
}

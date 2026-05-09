/**
 * Top-level inbox page consuming the existing /api/email surface.
 *
 * The CRM stores emails per-entity (each thread is anchored to a
 * contact / lead / opportunity / etc.) so the Inbox is intentionally a
 * *finder* rather than a Gmail clone — every result links back to the
 * entity detail page where the full thread + reply UI already lives
 * (see `EmailThread.tsx` and the `?tab=emails&email=<kind>:<id>` deep
 * link contract introduced for `EmailSearchModal.tsx`).
 *
 * Default view: most recent sent emails (uses the existing
 * ``/api/email`` list endpoint, scoped by the backend to the caller's
 * participation unless the caller is a superuser).
 *
 * With a search query: hits ``/api/email/search`` for unified
 * across-thread results (sent + received).
 *
 * Volume tile: ``/api/email/volume-stats`` so admins watching the
 * Gmail rate-limit don't have to dig into Settings.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  emailApi,
  getVolumeStats,
  type EmailQueueItem,
  type EmailSearchResult,
} from '../../api/email';
import { Spinner } from '../../components/ui';
import { ErrorEmptyState } from '../../components/ui/EmptyState';
import { usePageTitle } from '../../hooks/usePageTitle';

const SEARCH_ICON = (
  <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
  </svg>
);

const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'sent', label: 'Sent' },
  { value: 'pending', label: 'Pending' },
  { value: 'failed', label: 'Failed' },
] as const;

function formatTimestamp(value: string | null): string {
  if (!value) return '';
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  );
}

function VolumeTile() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['email', 'volume-stats'] as const,
    queryFn: getVolumeStats,
    staleTime: 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3">
        <Spinner size="sm" />
      </div>
    );
  }
  if (isError || !data) {
    // Surface the gap explicitly so an admin watching the rate-limit
    // doesn't mistake a broken telemetry endpoint (auth expired, Gmail
    // disconnected, 500) for "no emails sent today".
    return (
      <div
        className="rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3 min-w-[220px] text-xs text-gray-500 dark:text-gray-400"
        aria-label="Email volume unavailable"
      >
        Volume unavailable
      </div>
    );
  }

  const limit = data.warmup_enabled && data.warmup_current_limit > 0 ? data.warmup_current_limit : data.daily_limit;
  const ratio = limit > 0 ? Math.min(data.sent_today / limit, 1) : 0;

  return (
    <div
      className="rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3 min-w-[220px]"
      aria-label="Email volume today"
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-xs text-gray-500 dark:text-gray-400">Sent today</span>
        <span className="text-sm font-medium text-gray-900 dark:text-gray-100 tabular-nums">
          {data.sent_today} / {limit}
        </span>
      </div>
      <div className="mt-2 h-1.5 rounded-full bg-gray-100 dark:bg-gray-700 overflow-hidden">
        <div
          className="h-full rounded-full bg-primary-500"
          style={{ width: `${ratio * 100}%` }}
          role="progressbar"
          aria-valuenow={data.sent_today}
          aria-valuemin={0}
          aria-valuemax={limit}
        />
      </div>
      {data.warmup_enabled && (
        <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
          Warmup day {data.warmup_day}
        </p>
      )}
    </div>
  );
}

interface RecentRow {
  key: string;
  id: number;
  kind: 'sent' | 'received';
  subject: string;
  snippet: string;
  who: string;
  whoLabel: string; // "To:" or "From:"
  timestamp: string | null;
  entityType: string | null;
  entityId: number | null;
}

function searchToRow(item: EmailSearchResult): RecentRow {
  return {
    key: `${item.kind}-${item.id}`,
    id: item.id,
    kind: item.kind,
    subject: item.subject || '(No subject)',
    snippet: item.snippet || '',
    who: item.kind === 'sent' ? item.to_email : item.from_email || 'Unknown',
    whoLabel: item.kind === 'sent' ? 'To' : 'From',
    timestamp: item.sent_at,
    entityType: item.entity_type,
    entityId: item.entity_id,
  };
}

function listToRow(item: EmailQueueItem): RecentRow {
  // /api/email list returns outbound queue rows; strip HTML for the snippet
  // preview since the row links out to the entity page for full rendering.
  const stripped = (item.body || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  return {
    key: `sent-${item.id}`,
    id: item.id,
    kind: 'sent',
    subject: item.subject || '(No subject)',
    snippet: stripped.slice(0, 140),
    who: item.to_email,
    whoLabel: 'To',
    timestamp: item.sent_at || item.created_at,
    entityType: item.entity_type,
    entityId: item.entity_id,
  };
}

interface RowContentProps {
  row: RecentRow;
  navigable: boolean;
}

function RowContent({ row, navigable }: RowContentProps) {
  const kindClass =
    row.kind === 'sent'
      ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
      : 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300';
  return (
    <div className="flex items-start justify-between gap-3 min-w-0">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-0.5">
          <span className={`shrink-0 inline-block text-xs font-medium px-1.5 py-0.5 rounded ${kindClass}`}>
            {row.kind === 'sent' ? 'Sent' : 'Received'}
          </span>
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
            {row.subject}
          </span>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
          {row.whoLabel}: {row.who}
        </p>
        {row.snippet && (
          <p className="text-xs text-gray-400 dark:text-gray-500 truncate mt-0.5">{row.snippet}</p>
        )}
        {!navigable && (
          <p
            className="text-xs text-amber-500 dark:text-amber-400 mt-0.5"
            title="Ask an admin to relink this email — Settings → Email integrations"
          >
            Not linked to a contact yet
          </p>
        )}
      </div>
      {row.timestamp && (
        <span className="shrink-0 text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
          {formatTimestamp(row.timestamp)}
        </span>
      )}
    </div>
  );
}

function InboxPage() {
  usePageTitle('Inbox');
  const navigate = useNavigate();

  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  const isSearching = debouncedQuery.length > 0;

  // Default view: recent outbound (the only feed currently exposed
  // server-side that isn't entity-scoped). Search view: unified hits.
  const recentList = useQuery({
    queryKey: ['email', 'inbox-recent', statusFilter] as const,
    queryFn: () => emailApi.list({ page_size: 50, status: statusFilter || undefined }),
    enabled: !isSearching,
  });

  const searchResults = useQuery({
    queryKey: ['email', 'inbox-search', debouncedQuery] as const,
    queryFn: () => emailApi.search({ q: debouncedQuery, page_size: 50 }),
    enabled: isSearching,
  });

  const rows: RecentRow[] = useMemo(() => {
    if (isSearching) {
      return (searchResults.data?.items ?? []).map(searchToRow);
    }
    return (recentList.data?.items ?? []).map(listToRow);
  }, [isSearching, recentList.data, searchResults.data]);

  const total = isSearching ? searchResults.data?.total ?? 0 : recentList.data?.total ?? 0;
  const isLoading = isSearching ? searchResults.isLoading : recentList.isLoading;
  const error = isSearching ? searchResults.error : recentList.error;

  const handleRowClick = (row: RecentRow) => {
    if (row.entityType && row.entityId != null) {
      const target = `${row.kind}:${row.id}`;
      navigate(`/${row.entityType}/${row.entityId}?tab=emails&email=${encodeURIComponent(target)}`);
    }
  };

  const handleRowKeyDown = (e: React.KeyboardEvent, row: RecentRow) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleRowClick(row);
    }
  };

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Inbox</h1>
          <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            Recent emails across your CRM. Click any row to open the contact thread.
          </p>
        </div>
        <VolumeTile />
      </div>

      <div className="rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <label className="flex-1 flex items-center gap-3" htmlFor="inbox-search">
            {SEARCH_ICON}
            <input
              id="inbox-search"
              type="search"
              className="flex-1 bg-transparent text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none"
              placeholder="Search emails by subject, body, sender, or recipient..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              spellCheck={false}
              autoComplete="off"
            />
            {(searchResults.isFetching || recentList.isFetching) && <Spinner size="sm" />}
          </label>
        </div>

        {!isSearching && (
          <div className="flex flex-wrap items-center gap-2 px-4 py-2 border-b border-gray-100 dark:border-gray-700">
            <span className="text-xs text-gray-500 dark:text-gray-400 mr-1">Status:</span>
            {STATUS_FILTERS.map((f) => {
              const active = statusFilter === f.value;
              return (
                <button
                  key={f.value || 'all'}
                  type="button"
                  onClick={() => setStatusFilter(f.value)}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    active
                      ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 border-primary-200 dark:border-primary-700'
                      : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                  }`}
                  aria-pressed={active}
                >
                  {f.label}
                </button>
              );
            })}
          </div>
        )}

        {error ? (
          <ErrorEmptyState onRetry={() => (isSearching ? searchResults.refetch() : recentList.refetch())} />
        ) : isLoading ? (
          <div className="px-4 py-12 flex justify-center">
            <Spinner />
          </div>
        ) : rows.length === 0 ? (
          <p className="px-4 py-12 text-sm text-center text-gray-500 dark:text-gray-400">
            {isSearching ? `No emails found for "${debouncedQuery}"` : 'No emails to show yet.'}
          </p>
        ) : (
          <>
            <p className="px-4 py-2 text-xs text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-700">
              {total} {isSearching ? 'result' : 'email'}{total !== 1 ? 's' : ''}
              {total > rows.length ? ` (showing first ${rows.length})` : ''}
            </p>
            <ul role="list">
              {rows.map((row) => {
                const navigable = row.entityType != null && row.entityId != null;
                const baseClass =
                  'w-full text-left px-4 py-3 border-b border-gray-100 dark:border-gray-700/50 last:border-0';
                return (
                  <li key={row.key}>
                    {navigable ? (
                      <button
                        type="button"
                        onClick={() => handleRowClick(row)}
                        onKeyDown={(e) => handleRowKeyDown(e, row)}
                        aria-label={`${row.kind === 'sent' ? 'Sent' : 'Received'}: ${row.subject}`}
                        className={`${baseClass} hover:bg-gray-50 dark:hover:bg-gray-700/60 focus-visible:outline-none focus-visible:bg-gray-50 dark:focus-visible:bg-gray-700/60 cursor-pointer`}
                      >
                        <RowContent row={row} navigable />
                      </button>
                    ) : (
                      <div className={`${baseClass} opacity-75`}>
                        <RowContent row={row} navigable={false} />
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

export default InboxPage;

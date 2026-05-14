/**
 * Top-level inbox page consuming the existing /api/email surface.
 *
 * The CRM stores emails per-entity (each thread is anchored to a
 * contact / lead / etc.) so the Inbox is intentionally a
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

import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { MagnifyingGlassIcon } from '@heroicons/react/24/outline';
import {
  emailApi,
  type EmailQueueItem,
  type EmailSearchResult,
} from '../../api/email';
import { useVolumeStats } from '../../hooks/useEmail';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { Button, Spinner } from '../../components/ui';
import { ErrorEmptyState } from '../../components/ui/EmptyState';
import { PaginationBar } from '../../components/ui/Pagination';
import { usePageTitle } from '../../hooks/usePageTitle';
import { formatDateTime } from '../../utils/formatters';

const PAGE_SIZE = 25;

const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'sent', label: 'Sent' },
  { value: 'pending', label: 'Pending' },
  { value: 'failed', label: 'Failed' },
] as const;

type StatusValue = (typeof STATUS_FILTERS)[number]['value'];

function isStatusValue(value: string): value is StatusValue {
  return STATUS_FILTERS.some((f) => f.value === value);
}

function getErrorDetail(error: unknown): string | undefined {
  // apiClient rejects with ApiError ({ detail: string }); axios pre-interceptor
  // and unexpected throws surface as Error instances. FastAPI 422 responses
  // arrive here with `detail` as an array of {loc, msg, type} — the apiClient
  // only flattens that for blob bodies, so we flatten the JSON shape here.
  if (error && typeof error === 'object' && 'detail' in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) =>
          typeof d === 'object' && d !== null && typeof (d as { msg?: unknown }).msg === 'string'
            ? (d as { msg: string }).msg
            : null,
        )
        .filter((m): m is string => m !== null);
      if (msgs.length > 0) return msgs.join('; ');
    }
  }
  if (error instanceof Error && error.message) return error.message;
  return undefined;
}

function VolumeTile() {
  const { data, isLoading, isError } = useVolumeStats();

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

  const limit =
    data.warmup_enabled && data.warmup_current_limit > 0
      ? data.warmup_current_limit
      : data.daily_limit;
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

function RowContent({ row, navigable }: { row: RecentRow; navigable: boolean }) {
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
          {formatDateTime(row.timestamp)}
        </span>
      )}
    </div>
  );
}

function InboxPage() {
  usePageTitle('Inbox');
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const urlQuery = searchParams.get('q') ?? '';
  const urlStatus = searchParams.get('status') ?? '';
  const urlPage = Math.max(1, Number(searchParams.get('page') ?? '1') || 1);

  // Local typing state — debounced into the URL so the address bar
  // doesn't churn on every keystroke. URL is the source of truth for the
  // fetch (shareable + back-button friendly).
  const [query, setQuery] = useState(urlQuery);
  const debouncedQuery = useDebouncedValue(query, 300);

  const statusFilter: StatusValue = isStatusValue(urlStatus) ? urlStatus : '';

  // Set-or-delete a single URL param. Filter/query changes also clear
  // ?page= since the old offset is meaningless against the new result set.
  const updateParam = (key: 'q' | 'status' | 'page', value: string) => {
    setSearchParams(
      (prev) => {
        if (value) prev.set(key, value);
        else prev.delete(key);
        if (key !== 'page') prev.delete('page');
        return prev;
      },
      { replace: true },
    );
  };

  // Sync debounced query → URL ?q=.
  useEffect(() => {
    if (debouncedQuery === urlQuery) return;
    setSearchParams(
      (prev) => {
        if (debouncedQuery) prev.set('q', debouncedQuery);
        else prev.delete('q');
        prev.delete('page');
        return prev;
      },
      { replace: true },
    );
  }, [debouncedQuery, urlQuery, setSearchParams]);

  const setStatus = (value: StatusValue) => updateParam('status', value);
  const setPage = (page: number) => updateParam('page', page > 1 ? String(page) : '');

  const isSearching = debouncedQuery.length > 0;

  const recentList = useQuery({
    queryKey: ['email', 'inbox-recent', statusFilter, urlPage] as const,
    queryFn: () =>
      emailApi.list({
        page: urlPage,
        page_size: PAGE_SIZE,
        status: statusFilter || undefined,
      }),
    enabled: !isSearching,
  });

  const searchResults = useQuery({
    queryKey: ['email', 'inbox-search', debouncedQuery, urlPage] as const,
    queryFn: () =>
      emailApi.search({
        q: debouncedQuery,
        page: urlPage,
        page_size: PAGE_SIZE,
      }),
    enabled: isSearching,
  });

  const active = isSearching ? searchResults : recentList;

  const rows: RecentRow[] = useMemo(() => {
    if (isSearching) {
      return (searchResults.data?.items ?? []).map(searchToRow);
    }
    return (recentList.data?.items ?? []).map(listToRow);
  }, [isSearching, recentList.data, searchResults.data]);

  const total = active.data?.total ?? 0;
  const pages = active.data?.pages ?? 1;

  const handleRowClick = (row: RecentRow) => {
    if (row.entityType && row.entityId != null) {
      const target = `${row.kind}:${row.id}`;
      navigate(`/${row.entityType}/${row.entityId}?tab=emails&email=${encodeURIComponent(target)}`);
    }
  };

  const errorDetail = active.error ? getErrorDetail(active.error) : undefined;
  const statusLabel = STATUS_FILTERS.find((f) => f.value === statusFilter)?.label;
  const emptyMessage = isSearching
    ? `No emails found for "${debouncedQuery}"`
    : statusFilter
      ? `No emails matching ${statusLabel}.`
      : 'No emails to show yet.';

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
            <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
            <input
              id="inbox-search"
              type="search"
              className="flex-1 bg-transparent text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none"
              placeholder="Search emails by subject, body, sender, or recipient..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              spellCheck={false}
              autoComplete="off"
              maxLength={200}
            />
            {active.isFetching && <Spinner size="sm" />}
          </label>
        </div>

        {!isSearching && (
          <div className="flex flex-wrap items-center gap-2 px-4 py-2 border-b border-gray-100 dark:border-gray-700">
            <span className="text-xs text-gray-500 dark:text-gray-400 mr-1">Status:</span>
            {STATUS_FILTERS.map((f) => {
              const isActive = statusFilter === f.value;
              return (
                <button
                  key={f.value || 'all'}
                  type="button"
                  onClick={() => setStatus(f.value)}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    isActive
                      ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 border-primary-200 dark:border-primary-700'
                      : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                  }`}
                  aria-pressed={isActive}
                >
                  {f.label}
                </button>
              );
            })}
          </div>
        )}

        {active.error ? (
          <div className="px-4 py-8">
            <ErrorEmptyState description={errorDetail} onRetry={() => active.refetch()} />
          </div>
        ) : active.isLoading ? (
          <div className="px-4 py-12 flex justify-center">
            <Spinner />
          </div>
        ) : rows.length === 0 ? (
          <div
            className="px-4 py-12 flex flex-col items-center gap-2"
            aria-live="polite"
          >
            <p className="text-sm text-center text-gray-500 dark:text-gray-400">{emptyMessage}</p>
            {!isSearching && statusFilter && (
              <Button variant="secondary" size="sm" onClick={() => setStatus('')}>
                Clear filter
              </Button>
            )}
          </div>
        ) : (
          <>
            <p className="px-4 py-2 text-xs text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-700">
              {total} {isSearching ? 'result' : 'email'}{total !== 1 ? 's' : ''}
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
            <PaginationBar
              page={urlPage}
              pages={pages}
              total={total}
              pageSize={PAGE_SIZE}
              onPageChange={setPage}
            />
          </>
        )}
      </div>
    </div>
  );
}

export default InboxPage;

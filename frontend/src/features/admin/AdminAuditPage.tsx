import { useEffect, useMemo, useState } from 'react';
import {
  ArrowDownTrayIcon,
  ArrowPathIcon,
  ClockIcon,
  DocumentMagnifyingGlassIcon,
  LockClosedIcon,
  ShieldExclamationIcon,
  UsersIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

import { auditApi } from '../../api/audit';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { EntityLink } from '../../components/ui/EntityLink';
import { normalizeEntityType } from '../../components/ui/EntityLink.utils';
import { Input } from '../../components/ui/Input';
import { PaginationBar } from '../../components/ui/Pagination';
import { Select } from '../../components/ui/Select';
import { Spinner } from '../../components/ui/Spinner';
import { Table, type Column } from '../../components/ui/Table';
import { TabBar } from '../../components/shared/DetailPageShell';
import {
  useAdminAuditFeed,
  useAdminAuditEntityDetail,
  useAdminAuditSummary,
  useAdminAuditUserDetail,
} from '../../hooks/useAudit';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useAuthStore } from '../../store/authStore';
import type {
  AdminAuditEntitySummary,
  AdminAuditFeedItem,
  AdminAuditFeedResponse,
  AdminAuditSecurityEvent,
  AdminAuditSummaryResponse,
  AdminAuditUserDetail,
  AdminAuditUserSummary,
  AdminAuditEntityDetail,
  WorkSession,
} from '../../types';

type TabId = 'feed' | 'users' | 'entities' | 'security';

const TABS: { id: TabId; name: string }[] = [
  { id: 'feed', name: 'Live Feed' },
  { id: 'users', name: 'Time by Rep' },
  { id: 'entities', name: 'Entities' },
  { id: 'security', name: 'Security' },
];

const PAGE_SIZE = 50;

/** Replaces a 3-deep nested ternary in the header — the count label is
 *  per-tab so the JSX stays the same shape regardless of which tab is
 *  active. */
function tabCountLabel(
  activeTab: TabId,
  feed: AdminAuditFeedResponse | undefined,
  summary: AdminAuditSummaryResponse | undefined,
): string {
  const fmt = (n: number) => n.toLocaleString();
  switch (activeTab) {
    case 'feed':
      return `${fmt(feed?.total ?? 0)} matching audit events`;
    case 'users':
      return `${fmt(summary?.users.length ?? 0)} reps`;
    case 'entities':
      return `${fmt(summary?.entities.length ?? 0)} touched entities`;
    case 'security':
      return `${fmt(summary?.security.length ?? 0)} security signals`;
  }
}

/** Severity → Badge variant lookup. Unknown severities (e.g. backend
 *  added a new tier we haven't taught the UI about) fall back to gray. */
const SEVERITY_BADGE: Record<string, 'red' | 'yellow' | 'gray'> = {
  high: 'red',
  medium: 'yellow',
  low: 'gray',
};
function severityBadgeVariant(severity: string): 'red' | 'yellow' | 'gray' {
  return SEVERITY_BADGE[severity] ?? 'gray';
}

const DATE_PRESETS = [
  { label: 'Today', days: 0 },
  { label: '7d', days: 7 },
  { label: '30d', days: 30 },
  { label: '90d', days: 90 },
];

const ENTITY_OPTIONS = [
  { value: '', label: 'All entities' },
  { value: 'contacts', label: 'Contacts' },
  { value: 'companies', label: 'Companies' },
  { value: 'leads', label: 'Leads' },
  { value: 'proposals', label: 'Proposals' },
  { value: 'payments', label: 'Payments' },
  { value: 'campaigns', label: 'Campaigns' },
  { value: 'opportunities', label: 'Opportunities (legacy)' },
];

const ACTION_OPTIONS = [
  { value: '', label: 'All actions' },
  { value: 'create', label: 'Create' },
  { value: 'update', label: 'Update' },
  { value: 'delete', label: 'Delete' },
  { value: 'share', label: 'Share' },
  { value: 'unshare', label: 'Unshare' },
  { value: 'merge', label: 'Merge' },
  { value: 'import_merge', label: 'Import merge' },
];

const ACTION_BADGES: Record<string, 'green' | 'blue' | 'red' | 'yellow' | 'gray'> = {
  create: 'green',
  update: 'blue',
  delete: 'red',
  share: 'yellow',
  unshare: 'yellow',
  merge: 'gray',
  import_merge: 'yellow',
};

function isoDateDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

function formatDateTime(value?: string | null): string {
  if (!value) return '-';
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

function formatEntityLabel(entityType: string, entityId: number, label?: string | null) {
  const normalized = normalizeEntityType(entityType);
  const text = label || `${entityType} #${entityId}`;
  if (!normalized) return <span>{text}</span>;
  return (
    <EntityLink type={normalized} id={entityId} variant="primary">
      {text}
    </EntityLink>
  );
}

function formatChangePreview(changes: AdminAuditFeedItem['changes']): string {
  if (!changes) return 'No field changes';
  if (Array.isArray(changes)) {
    if (!changes.length) return 'No field changes';
    return changes
      .slice(0, 3)
      .map((change) => change.field || 'field')
      .join(', ');
  }
  return Object.keys(changes).slice(0, 3).join(', ') || 'Details recorded';
}

function csvCell(value: unknown): string {
  const text = value == null ? '' : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function downloadVisibleFeedCsv(
  rows: AdminAuditFeedItem[],
  context: { page: number; pageSize: number; totalRows: number | null },
) {
  const headers = ['time', 'user', 'email', 'action', 'entity_type', 'entity_id', 'ip_address', 'changes'];
  // Footer makes it impossible to confuse "Export visible" with "Export
  // everything matching the filter". Compliance pulls or security
  // audits need the full set — render the gap explicitly.
  const totalRowsText =
    context.totalRows != null ? String(context.totalRows) : 'unknown';
  const lines = [
    headers.map(csvCell).join(','),
    ...rows.map((row) => [
      row.created_at,
      row.user_name || 'System',
      row.user_email || '',
      row.action,
      row.entity_type,
      row.entity_id,
      row.ip_address || '',
      formatChangePreview(row.changes),
    ].map(csvCell).join(',')),
    csvCell(
      `# Visible page ${context.page} of ${rows.length}-row chunks ` +
        `(page size ${context.pageSize}). Filter total: ${totalRowsText} ` +
        `rows. Re-run with a narrower date range for a complete export.`,
    ),
  ];
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `crm-audit-feed-${new Date().toISOString().slice(0, 10)}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function exportFullFilter(
  filters: Record<string, string | number | undefined>,
  setBusy: (busy: boolean) => void,
  setError: (msg: string | null) => void,
) {
  setBusy(true);
  setError(null);
  try {
    const blob = await auditApi.exportAdminAuditCsv(filters);
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `crm-audit-${new Date().toISOString().slice(0, 10)}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error('[audit] full export failed', err);
    setError('Export failed — narrow the filter and retry, or check server logs.');
  } finally {
    setBusy(false);
  }
}

function MetricCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <Card padding="sm" shadow="sm">
      <div className="flex items-center gap-3">
        <div className="rounded-md bg-gray-100 p-2 dark:bg-gray-700">
          <Icon className="h-5 w-5 text-gray-600 dark:text-gray-300" />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase text-gray-500 dark:text-gray-400">
            {label}
          </p>
          <p className="text-xl font-semibold text-gray-900 dark:text-gray-100 tabular-nums">
            {value}
          </p>
        </div>
      </div>
    </Card>
  );
}

function AuditDrawer({
  event,
  onClose,
}: {
  event: AdminAuditFeedItem | null;
  onClose: () => void;
}) {
  if (!event) return null;
  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        className="absolute inset-0 bg-black/20"
        aria-label="Close audit details"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="audit-drawer-title"
        className="absolute right-0 top-0 h-full w-full max-w-xl overflow-y-auto bg-white p-5 shadow-xl dark:bg-gray-800"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="audit-drawer-title" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Audit event #{event.id}
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {formatDateTime(event.created_at)}
            </p>
          </div>
          <button
            type="button"
            className="rounded-md p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700"
            onClick={onClose}
          >
            <span className="sr-only">Close</span>
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        <dl className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium uppercase text-gray-500 dark:text-gray-400">User</dt>
            <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
              {event.user_name || 'System'}
              {event.user_email ? (
                <span className="block text-xs text-gray-500 dark:text-gray-400">
                  {event.user_email}
                </span>
              ) : null}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase text-gray-500 dark:text-gray-400">Action</dt>
            <dd className="mt-1">
              <Badge variant={ACTION_BADGES[event.action] ?? 'gray'} size="sm">
                {event.action}
              </Badge>
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase text-gray-500 dark:text-gray-400">Entity</dt>
            <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
              {formatEntityLabel(event.entity_type, event.entity_id)}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase text-gray-500 dark:text-gray-400">IP address</dt>
            <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{event.ip_address || '-'}</dd>
          </div>
        </dl>

        <div className="mt-6">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Changes</h3>
          <pre className="mt-2 max-h-[28rem] overflow-auto rounded-md bg-gray-950 p-4 text-xs text-gray-100">
            {JSON.stringify(event.changes ?? {}, null, 2)}
          </pre>
        </div>
      </aside>
    </div>
  );
}

function DrawerFrame({
  title,
  subtitle,
  children,
  onClose,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        className="absolute inset-0 bg-black/20"
        aria-label={`Close ${title}`}
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="audit-detail-drawer-title"
        className="absolute right-0 top-0 h-full w-full max-w-2xl overflow-y-auto bg-white p-5 shadow-xl dark:bg-gray-800"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="audit-detail-drawer-title" className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {title}
            </h2>
            {subtitle ? (
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>
            ) : null}
          </div>
          <button
            type="button"
            className="rounded-md p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700"
            onClick={onClose}
          >
            <span className="sr-only">Close</span>
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>
        {children}
      </aside>
    </div>
  );
}

function DetailMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-gray-200 p-3 dark:border-gray-700">
      <p className="text-xs font-medium uppercase text-gray-500 dark:text-gray-400">{label}</p>
      <p className="mt-1 text-base font-semibold text-gray-900 dark:text-gray-100 tabular-nums">
        {value}
      </p>
    </div>
  );
}

function SessionList({ sessions }: { sessions: WorkSession[] }) {
  if (!sessions.length) {
    return <p className="py-4 text-sm text-gray-500 dark:text-gray-400">No active-time sessions in this period.</p>;
  }
  return (
    <div className="divide-y divide-gray-200 rounded-md border border-gray-200 dark:divide-gray-700 dark:border-gray-700">
      {sessions.slice(0, 8).map((session) => (
        <div key={session.id} className="grid grid-cols-1 gap-2 p-3 text-sm sm:grid-cols-[1fr_auto]">
          <div>
            <p className="font-medium text-gray-900 dark:text-gray-100">
              {formatEntityLabel(session.entity_type, session.entity_id)}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {formatDateTime(session.started_at)} - {formatDateTime(session.last_seen_at)}
            </p>
          </div>
          <span className="font-medium text-gray-700 dark:text-gray-200 tabular-nums">
            {formatDuration(session.duration_seconds)}
          </span>
        </div>
      ))}
    </div>
  );
}

function RecentEventList({ rows }: { rows: AdminAuditFeedItem[] }) {
  if (!rows.length) {
    return <p className="py-4 text-sm text-gray-500 dark:text-gray-400">No audit events in this period.</p>;
  }
  return (
    <div className="divide-y divide-gray-200 rounded-md border border-gray-200 dark:divide-gray-700 dark:border-gray-700">
      {rows.slice(0, 8).map((row) => (
        <div key={row.id} className="grid grid-cols-1 gap-2 p-3 text-sm sm:grid-cols-[auto_1fr_auto]">
          <Badge variant={ACTION_BADGES[row.action] ?? 'gray'} size="sm">
            {row.action}
          </Badge>
          <div className="min-w-0">
            <p className="truncate text-gray-900 dark:text-gray-100">
              {formatEntityLabel(row.entity_type, row.entity_id)}
            </p>
            <p className="truncate text-xs text-gray-500 dark:text-gray-400">
              {formatChangePreview(row.changes)}
            </p>
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400">{formatDateTime(row.created_at)}</span>
        </div>
      ))}
    </div>
  );
}

function UserDetailDrawer({
  user,
  detail,
  isLoading,
  onClose,
}: {
  user: AdminAuditUserSummary | null;
  detail?: AdminAuditUserDetail;
  isLoading: boolean;
  onClose: () => void;
}) {
  if (!user) return null;
  const summary = detail?.summary ?? user;
  return (
    <DrawerFrame
      title={summary.user_name}
      subtitle="Rep activity, sessions, and audit trail"
      onClose={onClose}
    >
      {isLoading ? (
        <div className="flex justify-center py-12"><Spinner /></div>
      ) : (
        <div className="mt-6 space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <DetailMetric label="Estimated Active CRM Time" value={formatDuration(summary.active_crm_seconds)} />
            <DetailMetric label="Audit Events" value={summary.audit_events} />
            <DetailMetric label="Calls" value={summary.calls} />
            <DetailMetric label="Emails" value={summary.emails} />
          </div>
          <section>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Recent active-time sessions</h3>
            <div className="mt-2">
              <SessionList sessions={detail?.sessions ?? []} />
            </div>
          </section>
          <section>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Recent audit events</h3>
            <div className="mt-2">
              <RecentEventList rows={detail?.feed.items ?? []} />
            </div>
          </section>
        </div>
      )}
    </DrawerFrame>
  );
}

function EntityDetailDrawer({
  entity,
  detail,
  isLoading,
  onClose,
}: {
  entity: AdminAuditEntitySummary | null;
  detail?: AdminAuditEntityDetail;
  isLoading: boolean;
  onClose: () => void;
}) {
  if (!entity) return null;
  const summary = detail?.summary ?? entity;
  return (
    <DrawerFrame
      title={summary.label || `${summary.entity_type} #${summary.entity_id}`}
      subtitle="Entity time, touches, and audit trail"
      onClose={onClose}
    >
      {isLoading ? (
        <div className="flex justify-center py-12"><Spinner /></div>
      ) : (
        <div className="mt-6 space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <DetailMetric label="Estimated Active CRM Time" value={formatDuration(summary.active_crm_seconds)} />
            <DetailMetric label="Activities" value={summary.activity_count} />
            <DetailMetric label="Audit Events" value={summary.audit_count} />
            <DetailMetric label="Owner" value={summary.owner_name || '-'} />
          </div>
          <section>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Recent active-time sessions</h3>
            <div className="mt-2">
              <SessionList sessions={detail?.sessions ?? []} />
            </div>
          </section>
          <section>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Recent audit events</h3>
            <div className="mt-2">
              <RecentEventList rows={detail?.feed.items ?? []} />
            </div>
          </section>
        </div>
      )}
    </DrawerFrame>
  );
}

// The audit feed auto-refetches every 120s (lowered from 30s to cut Neon
// cost; see useAudit.ts). Admins acting on stale data could revoke a
// session that was already restored, so surface the staleness explicitly.
// Amber kicks in past 60s — about the human threshold for "I should hit
// Refresh before I act". `tick` is the parent's 10s heartbeat that ages
// the label between refetches.
function FeedStalenessBadge({
  updatedAt,
  isFetching,
  tick: _tick,
}: {
  updatedAt: number;
  isFetching: boolean;
  tick: number;
}) {
  if (!updatedAt) return null;
  const ageSec = Math.max(0, Math.floor((Date.now() - updatedAt) / 1000));
  const label = isFetching
    ? 'Refreshing…'
    : ageSec < 5
      ? 'Updated just now'
      : ageSec < 60
        ? `Updated ${ageSec}s ago`
        : `Updated ${Math.floor(ageSec / 60)}m ago`;
  const stale = !isFetching && ageSec >= 60;
  return (
    <span
      role="status"
      aria-live="polite"
      className={
        stale
          ? 'inline-flex items-center self-center rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-200'
          : 'inline-flex items-center self-center rounded-md border border-gray-200 bg-gray-50 px-2 py-1 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300'
      }
      title={new Date(updatedAt).toLocaleString()}
    >
      {label}
    </span>
  );
}

export default function AdminAuditPage() {
  usePageTitle('Audit - Admin');

  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.is_superuser || user?.role === 'admin';

  const [activeTab, setActiveTab] = useState<TabId>('feed');
  const [page, setPage] = useState(1);
  const [startDate, setStartDate] = useState(isoDateDaysAgo(7));
  const [endDate, setEndDate] = useState(isoDateDaysAgo(0));
  const [userId, setUserId] = useState('');
  const [entityType, setEntityType] = useState('');
  const [action, setAction] = useState('');
  const [search, setSearch] = useState('');
  const [selectedEvent, setSelectedEvent] = useState<AdminAuditFeedItem | null>(null);
  const [selectedUser, setSelectedUser] = useState<AdminAuditUserSummary | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<AdminAuditEntitySummary | null>(null);
  const [exportingFull, setExportingFull] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  // 10s tick so the staleness badge ages between the 120s auto-refetches.
  // Without this, the badge would only re-render when the query refires.
  const [staleTick, setStaleTick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setStaleTick((n) => n + 1), 10_000);
    return () => window.clearInterval(id);
  }, []);

  const summaryFilters = useMemo(() => ({
    start_date: startDate || undefined,
    end_date: endDate || undefined,
    user_id: userId ? Number(userId) : undefined,
    entity_type: entityType || undefined,
    action: action || undefined,
    search: search || undefined,
  }), [startDate, endDate, userId, entityType, action, search]);

  const feedFilters = useMemo(() => ({
    ...summaryFilters,
    page,
    page_size: PAGE_SIZE,
  }), [summaryFilters, page]);

  // Drawer queries reuse the dashboard filters minus entity_type
  // (the drawer is already scoped to one entity) and force first-page
  // pagination so the user always lands on the most recent slice.
  const detailFilters = useMemo(() => ({
    ...summaryFilters,
    entity_type: undefined,
    page: 1,
    page_size: 25,
  }), [summaryFilters]);

  const { data: summary, isLoading: summaryLoading, refetch: refetchSummary } =
    useAdminAuditSummary(summaryFilters);
  const {
    data: feed,
    isLoading: feedLoading,
    isFetching: feedFetching,
    dataUpdatedAt: feedUpdatedAt,
    refetch: refetchFeed,
  } = useAdminAuditFeed(feedFilters);
  const { data: selectedUserDetail, isLoading: userDetailLoading } =
    useAdminAuditUserDetail(selectedUser?.user_id ?? 0, detailFilters);
  const { data: selectedEntityDetail, isLoading: entityDetailLoading } =
    useAdminAuditEntityDetail(
      selectedEntity?.entity_type ?? '',
      selectedEntity?.entity_id ?? 0,
      detailFilters
    );

  const resetPage = () => setPage(1);
  const applyDatePreset = (days: number) => {
    setStartDate(isoDateDaysAgo(days));
    setEndDate(isoDateDaysAgo(0));
    resetPage();
  };
  const resetFilters = () => {
    setStartDate(isoDateDaysAgo(7));
    setEndDate(isoDateDaysAgo(0));
    setUserId('');
    setEntityType('');
    setAction('');
    setSearch('');
    resetPage();
  };

  const userOptions = [
    { value: '', label: 'All users' },
    ...(summary?.users ?? []).map((u) => ({
      value: String(u.user_id),
      label: u.user_name,
    })),
  ];

  const userColumns: Column<AdminAuditUserSummary>[] = [
    {
      key: 'user_name',
      header: 'Rep',
      render: (row) => (
        <div>
          <p className="font-medium text-gray-900 dark:text-gray-100">{row.user_name}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">{row.role || 'user'}</p>
        </div>
      ),
    },
    {
      key: 'active_crm_seconds',
      header: 'Estimated Active CRM Time',
      render: (row) => <span className="tabular-nums">{formatDuration(row.active_crm_seconds)}</span>,
    },
    { key: 'calls', header: 'Calls', render: (row) => <span className="tabular-nums">{row.calls}</span> },
    { key: 'emails', header: 'Emails', render: (row) => <span className="tabular-nums">{row.emails}</span> },
    { key: 'proposals_touched', header: 'Proposals', render: (row) => <span className="tabular-nums">{row.proposals_touched}</span> },
    { key: 'opportunities_touched', header: 'Opportunities', render: (row) => <span className="tabular-nums">{row.opportunities_touched}</span> },
    { key: 'last_active_at', header: 'Last Active', render: (row) => formatDateTime(row.last_active_at) },
    {
      key: 'inspect',
      header: '',
      render: (row) => (
        <Button variant="ghost" size="sm" onClick={() => setSelectedUser(row)}>
          Inspect
        </Button>
      ),
    },
  ];

  const entityColumns: Column<AdminAuditEntitySummary>[] = [
    {
      key: 'label',
      header: 'Entity',
      render: (row) => formatEntityLabel(row.entity_type, row.entity_id, row.label),
    },
    { key: 'owner_name', header: 'Owner', render: (row) => row.owner_name || '-' },
    {
      key: 'active_crm_seconds',
      header: 'Estimated Active CRM Time',
      render: (row) => <span className="tabular-nums">{formatDuration(row.active_crm_seconds)}</span>,
    },
    { key: 'activity_count', header: 'Activities', render: (row) => <span className="tabular-nums">{row.activity_count}</span> },
    { key: 'audit_count', header: 'Audit Events', render: (row) => <span className="tabular-nums">{row.audit_count}</span> },
    { key: 'last_touched_by_name', header: 'Last Touched By', render: (row) => row.last_touched_by_name || '-' },
    { key: 'last_touched_at', header: 'Last Touched', render: (row) => formatDateTime(row.last_touched_at) },
    {
      key: 'inspect',
      header: '',
      render: (row) => (
        <Button variant="ghost" size="sm" onClick={() => setSelectedEntity(row)}>
          Inspect
        </Button>
      ),
    },
  ];

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <LockClosedIcon className="mb-4 h-12 w-12 text-gray-400 dark:text-gray-500" />
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Access Denied</h1>
        <p className="mt-2 max-w-md text-sm text-gray-500 dark:text-gray-400">
          Only admins can view this page.
        </p>
      </div>
    );
  }

  const totals = summary?.totals;

  return (
    <div className="space-y-5" data-guide="admin-audit-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">CRM Audit</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Estimated active CRM time and audit activity
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            leftIcon={<ArrowDownTrayIcon className="h-4 w-4" />}
            onClick={() =>
              downloadVisibleFeedCsv(feed?.items ?? [], {
                page: feedFilters.page,
                pageSize: feedFilters.page_size,
                totalRows: feed?.total ?? null,
              })
            }
            disabled={!feed?.items.length}
            title={
              feed?.total != null
                ? `Exports the visible ${feed.items.length} row${feed.items.length === 1 ? '' : 's'} of ${feed.total} matching the current filter`
                : undefined
            }
          >
            {feed?.total != null
              ? `Export visible (${feed.items.length}/${feed.total})`
              : 'Export visible'}
          </Button>
          <Button
            variant="secondary"
            leftIcon={<ArrowDownTrayIcon className="h-4 w-4" />}
            onClick={() =>
              exportFullFilter(summaryFilters, setExportingFull, setExportError)
            }
            disabled={exportingFull || !feed?.total}
            title="Streams every audit row matching the current filter — for compliance pulls"
          >
            {exportingFull
              ? 'Exporting...'
              : feed?.total != null
                ? `Export filter (${feed.total.toLocaleString()})`
                : 'Export filter'}
          </Button>
          <FeedStalenessBadge
            updatedAt={feedUpdatedAt}
            isFetching={feedFetching}
            tick={staleTick}
          />
          <Button
            variant="secondary"
            leftIcon={<ArrowPathIcon className="h-4 w-4" />}
            onClick={() => {
              refetchSummary();
              refetchFeed();
            }}
          >
            Refresh
          </Button>
        </div>
      </div>

      {exportError && (
        <div
          role="alert"
          aria-live="polite"
          className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
        >
          {exportError}
          <button
            type="button"
            className="ml-3 text-xs underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
            onClick={() => setExportError(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard
          label="Active CRM time"
          value={totals ? formatDuration(totals.active_crm_seconds) : '-'}
          icon={ClockIcon}
        />
        <MetricCard
          label="Audit events"
          value={(totals?.audit_events ?? 0).toLocaleString()}
          icon={DocumentMagnifyingGlassIcon}
        />
        <MetricCard
          label="Users"
          value={(summary?.users.length ?? 0).toLocaleString()}
          icon={UsersIcon}
        />
        <MetricCard
          label="Calls"
          value={(totals?.calls ?? 0).toLocaleString()}
          icon={ClockIcon}
        />
        <MetricCard
          label="Security"
          value={(totals?.security_events ?? 0).toLocaleString()}
          icon={ShieldExclamationIcon}
        />
      </div>

      <Card padding="sm" shadow="sm">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2">
            {DATE_PRESETS.map((preset) => (
              <Button
                key={preset.label}
                variant="ghost"
                size="sm"
                onClick={() => applyDatePreset(preset.days)}
              >
                {preset.label}
              </Button>
            ))}
          </div>
          <Button variant="ghost" size="sm" onClick={resetFilters}>
            Reset filters
          </Button>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Input
            label="Start"
            type="date"
            value={startDate}
            onChange={(e) => {
              setStartDate(e.target.value);
              resetPage();
            }}
          />
          <Input
            label="End"
            type="date"
            value={endDate}
            onChange={(e) => {
              setEndDate(e.target.value);
              resetPage();
            }}
          />
          <Select
            label="User"
            value={userId}
            options={userOptions}
            onChange={(e) => {
              setUserId(e.target.value);
              resetPage();
            }}
          />
          <Select
            label="Entity"
            value={entityType}
            options={ENTITY_OPTIONS}
            onChange={(e) => {
              setEntityType(e.target.value);
              resetPage();
            }}
          />
          <Select
            label="Action"
            value={action}
            options={ACTION_OPTIONS}
            onChange={(e) => {
              setAction(e.target.value);
              resetPage();
            }}
          />
          <Input
            label="Search"
            value={search}
            placeholder="Name, action, diff"
            onChange={(e) => {
              setSearch(e.target.value);
              resetPage();
            }}
          />
        </div>
      </Card>

      <Card padding="none">
        <div className="flex flex-col gap-2 px-4 pt-2 sm:flex-row sm:items-center sm:justify-between">
          <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />
          <p className="pb-2 text-xs text-gray-500 dark:text-gray-400 sm:pb-0">
            {tabCountLabel(activeTab, feed, summary)}
          </p>
        </div>
        <div className="p-4">
          {activeTab === 'feed' && (
            <LiveFeedTable
              rows={feed?.items ?? []}
              isLoading={feedLoading}
              onSelect={setSelectedEvent}
            />
          )}
          {activeTab === 'users' && (
            <Table
              columns={userColumns}
              data={summary?.users ?? []}
              keyExtractor={(row) => row.user_id}
              isLoading={summaryLoading}
              emptyMessage="No user activity in this period"
            />
          )}
          {activeTab === 'entities' && (
            <Table
              columns={entityColumns}
              data={summary?.entities ?? []}
              keyExtractor={(row) => `${row.entity_type}-${row.entity_id}`}
              isLoading={summaryLoading}
              emptyMessage="No entity activity in this period"
            />
          )}
          {activeTab === 'security' && (
            <SecurityTable
              rows={summary?.security ?? []}
              isLoading={summaryLoading}
            />
          )}
        </div>
        {activeTab === 'feed' && feed ? (
          <PaginationBar
            page={feed.page}
            pages={feed.pages}
            total={feed.total}
            pageSize={feed.page_size}
            onPageChange={setPage}
          />
        ) : null}
      </Card>

      <AuditDrawer event={selectedEvent} onClose={() => setSelectedEvent(null)} />
      <UserDetailDrawer
        user={selectedUser}
        detail={selectedUserDetail}
        isLoading={userDetailLoading}
        onClose={() => setSelectedUser(null)}
      />
      <EntityDetailDrawer
        entity={selectedEntity}
        detail={selectedEntityDetail}
        isLoading={entityDetailLoading}
        onClose={() => setSelectedEntity(null)}
      />
    </div>
  );
}

function LiveFeedTable({
  rows,
  isLoading,
  onSelect,
}: {
  rows: AdminAuditFeedItem[];
  isLoading: boolean;
  onSelect: (row: AdminAuditFeedItem) => void;
}) {
  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }
  if (!rows.length) {
    return <p className="py-8 text-sm text-gray-500 dark:text-gray-400">No audit events match the current filters.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead className="bg-gray-50 dark:bg-gray-900">
          <tr>
            {['Time', 'User', 'Action', 'Entity', 'Diff Preview', ''].map((header) => (
              <th
                key={header}
                scope="col"
                className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500 dark:text-gray-400"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-700 dark:bg-gray-800">
          {rows.map((row) => (
            <tr key={row.id} className="hover:bg-gray-50 dark:hover:bg-gray-700/40">
              <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                {formatDateTime(row.created_at)}
              </td>
              <td className="px-4 py-3 text-sm">
                <p className="font-medium text-gray-900 dark:text-gray-100">
                  {row.user_name || 'System'}
                </p>
                {row.user_email ? (
                  <p className="text-xs text-gray-500 dark:text-gray-400">{row.user_email}</p>
                ) : null}
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                <Badge variant={ACTION_BADGES[row.action] ?? 'gray'} size="sm">
                  {row.action}
                </Badge>
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-sm">
                {formatEntityLabel(row.entity_type, row.entity_id)}
              </td>
              <td className="max-w-md px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                <span className="line-clamp-2">{formatChangePreview(row.changes)}</span>
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-right">
                <Button variant="ghost" size="sm" onClick={() => onSelect(row)}>
                  Details
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SecurityTable({
  rows,
  isLoading,
}: {
  rows: AdminAuditSecurityEvent[];
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }
  if (!rows.length) {
    return <p className="py-8 text-sm text-gray-500 dark:text-gray-400">No security events match the current filters.</p>;
  }
  return (
    <div className="space-y-3">
      {rows.map((event) => (
        <div
          key={event.id}
          className="rounded-md border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800"
        >
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <Badge
                variant={severityBadgeVariant(event.severity)}
                size="sm"
              >
                {event.severity}
              </Badge>
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {event.description}
              </span>
            </div>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {formatDateTime(event.created_at)}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500 dark:text-gray-400">
            <span>Category: {event.category}</span>
            {event.user_name ? <span>User: {event.user_name}</span> : null}
            {event.entity_type && event.entity_id ? (
              <span>
                Entity: {event.entity_type} #{event.entity_id}
              </span>
            ) : null}
            {event.count > 1 ? <span>Count: {event.count}</span> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

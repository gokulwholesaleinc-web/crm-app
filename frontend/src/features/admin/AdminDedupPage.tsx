/**
 * Admin /admin/dedup — browse duplicate clusters by email/phone/name and
 * collapse them via the existing /api/dedup/merge-cluster endpoint.
 *
 * Surfaces the data that the dedup-on-import wizard catches before it
 * happens; this page is for cleaning up duplicates that already exist
 * from prior imports.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { LockClosedIcon, ArrowPathIcon, UsersIcon } from '@heroicons/react/24/outline';

import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { Select } from '../../components/ui/Select';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { useAuthStore } from '../../store/authStore';
import { usePageTitle } from '../../hooks/usePageTitle';
import { showSuccess, showError } from '../../utils/toast';
import { formatDate } from '../../utils/formatters';
import {
  listDuplicateClusters,
  mergeCluster,
} from '../../api/dedup';
import type {
  DedupCluster,
  DedupClusterKey,
  DedupClusterMember,
  DedupEntityType,
  MergeClusterFailure,
  MergeClusterFailureCode,
} from '../../api/dedup';

const FAILURE_CODE_LABEL: Record<MergeClusterFailureCode, string> = {
  self_merge: 'Winner ID was in the loser list',
  stale_cluster: 'Already merged — refresh and retry',
  not_found_primary: 'Winner record no longer exists',
  other: 'Failed',
};

const ENTITY_OPTIONS: { value: DedupEntityType; label: string }[] = [
  { value: 'contacts', label: 'Contacts' },
  { value: 'companies', label: 'Companies' },
  { value: 'leads', label: 'Leads' },
];

const KEYS_BY_ENTITY: Record<DedupEntityType, { value: DedupClusterKey; label: string }[]> = {
  contacts: [
    { value: 'email', label: 'Email' },
    { value: 'phone', label: 'Phone' },
    { value: 'name', label: 'Name (first + last)' },
  ],
  companies: [
    { value: 'name', label: 'Name (normalized, suffixes stripped)' },
    { value: 'email', label: 'Email' },
    { value: 'phone', label: 'Phone' },
  ],
  leads: [
    { value: 'email', label: 'Email' },
    { value: 'phone', label: 'Phone' },
  ],
};

function detailHref(entityType: DedupEntityType, id: number): string {
  return `/${entityType}/${id}`;
}

interface ClusterCardProps {
  entityType: DedupEntityType;
  cluster: DedupCluster;
  busy: boolean;
  onMerge: (winnerId: number, loserIds: number[]) => void;
}

function ClusterCard({ entityType, cluster, busy, onMerge }: ClusterCardProps) {
  // Default: the most-recently-active member wins (backend already sorts
  // members by last_activity_at desc). Backend guarantees member_count >= 2
  // so members[0] is always defined, but TS doesn't know that.
  const defaultWinner = cluster.members[0]?.id ?? 0;
  const [winnerId, setWinnerId] = useState<number>(defaultWinner);
  const losers = cluster.members.filter((m) => m.id !== winnerId).map((m) => m.id);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4 space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
            {cluster.key} match
          </p>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
            {cluster.key_value}
          </h3>
        </div>
        <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">
          {cluster.member_count} record{cluster.member_count !== 1 ? 's' : ''}
        </span>
      </div>

      <ul className="space-y-1">
        {cluster.members.map((m) => (
          <ClusterMemberRow
            key={m.id}
            entityType={entityType}
            member={m}
            isWinner={m.id === winnerId}
            onPick={() => setWinnerId(m.id)}
          />
        ))}
      </ul>

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Button
          size="sm"
          onClick={() => onMerge(winnerId, losers)}
          isLoading={busy}
          disabled={losers.length === 0}
        >
          Merge {losers.length} into winner
        </Button>
        <span className="text-[11px] text-gray-500 dark:text-gray-400">
          Losers are soft-deleted; activities, opportunities, quotes, proposals, and contracts repoint to the winner.
        </span>
      </div>
    </div>
  );
}

interface ClusterMemberRowProps {
  entityType: DedupEntityType;
  member: DedupClusterMember;
  isWinner: boolean;
  onPick: () => void;
}

function ClusterMemberRow({ entityType, member, isWinner, onPick }: ClusterMemberRowProps) {
  return (
    <li className="flex items-center gap-3 p-2 rounded border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/30">
      <input
        type="radio"
        name={`winner-${member.id}-${entityType}`}
        checked={isWinner}
        onChange={onPick}
        aria-label={`Keep ${member.label}`}
        className="text-primary-600"
      />
      <div className="flex-1 min-w-0">
        <a
          href={detailHref(entityType, member.id)}
          className="text-sm font-medium text-primary-600 dark:text-primary-400 hover:underline truncate inline-block max-w-full"
        >
          {member.label}
        </a>
        <div className="flex flex-wrap gap-x-3 text-[11px] text-gray-600 dark:text-gray-400">
          {member.email && <span className="truncate">{member.email}</span>}
          {member.phone && <span>{member.phone}</span>}
          <span>
            {member.activity_count} activit{member.activity_count !== 1 ? 'ies' : 'y'}
          </span>
          {member.last_activity_at && (
            <span>last touched {formatDate(member.last_activity_at)}</span>
          )}
        </div>
      </div>
      {isWinner && (
        <span className="inline-flex items-center text-[10px] font-medium px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-300">
          Winner
        </span>
      )}
    </li>
  );
}

export default function AdminDedupPage() {
  usePageTitle('Duplicate Cleanup — Admin');

  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const queryClient = useQueryClient();

  const isAuthorized =
    user?.is_superuser || user?.role === 'admin' || user?.role === 'manager';

  const [entityType, setEntityType] = useState<DedupEntityType>('contacts');
  const [key, setKey] = useState<DedupClusterKey>('email');
  const [pendingMerge, setPendingMerge] = useState<{
    cluster: DedupCluster;
    winnerId: number;
    loserIds: number[];
  } | null>(null);
  const [lastFailures, setLastFailures] = useState<MergeClusterFailure[]>([]);

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ['admin', 'dedup', 'clusters', entityType, key],
    queryFn: () => listDuplicateClusters(entityType, key),
    enabled: isAuthorized,
  });

  const merge = useMutation({
    mutationFn: ({ winnerId, loserIds }: { winnerId: number; loserIds: number[] }) =>
      mergeCluster(entityType, winnerId, loserIds),
    onSuccess: (result) => {
      // Defensive: backend always returns success: true today, but if it
      // ever flips, branch first so we don't fire a success-shape toast
      // on a logical failure.
      if (!result.success) {
        showError('Merge failed — see server logs for details');
        setLastFailures(result.failures);
        setPendingMerge(null);
        return;
      }
      const failed = result.failures.length;
      if (failed > 0) {
        showError(
          `Merged ${result.merged_ids.length} of ${result.merged_ids.length + failed}; ${failed} failed — see details below`,
        );
        setLastFailures(result.failures);
      } else {
        showSuccess(`Merged ${result.merged_ids.length} record${result.merged_ids.length !== 1 ? 's' : ''} into the winner`);
        setLastFailures([]);
      }
      setPendingMerge(null);
      queryClient.invalidateQueries({ queryKey: ['admin', 'dedup', 'clusters', entityType, key] });
    },
    onError: (err) => {
      const message = err instanceof Error ? err.message : 'Merge failed';
      showError(message);
      setPendingMerge(null);
    },
  });

  if (!isAuthorized) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <LockClosedIcon
          className="h-12 w-12 text-gray-400 dark:text-gray-500 mb-4"
          aria-hidden="true"
        />
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
          Access Denied
        </h1>
        <p className="max-w-md text-sm text-gray-500 dark:text-gray-400">
          Only admins and managers can view this page.
        </p>
        <Button variant="secondary" className="mt-6" onClick={() => navigate('/')}>
          Go to Dashboard
        </Button>
      </div>
    );
  }

  const clusters = data?.clusters ?? [];
  const skippedNoKey = data?.skipped_no_key ?? 0;
  const totalDupes = clusters.reduce((sum, c) => sum + (c.member_count - 1), 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <UsersIcon className="h-6 w-6 text-gray-500 dark:text-gray-400" aria-hidden="true" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Duplicate Cleanup</h1>
          <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
            Find existing duplicates and collapse them into a single record. The dedup-on-import wizard prevents new ones; this is for backlog.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <Select
          id="dedup-entity"
          label="Entity type"
          value={entityType}
          options={ENTITY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          onChange={(e) => {
            const next = e.target.value as DedupEntityType;
            setEntityType(next);
            const firstKey = KEYS_BY_ENTITY[next][0]?.value ?? 'email';
            setKey(firstKey);
          }}
        />
        <Select
          id="dedup-key"
          label="Match on"
          value={key}
          options={KEYS_BY_ENTITY[entityType].map((o) => ({ value: o.value, label: o.label }))}
          onChange={(e) => setKey(e.target.value as DedupClusterKey)}
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => queryClient.invalidateQueries({ queryKey: ['admin', 'dedup', 'clusters'] })}
          leftIcon={<ArrowPathIcon className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} aria-hidden="true" />}
        >
          Refresh
        </Button>
        <div className="ml-auto text-sm text-gray-600 dark:text-gray-400" aria-live="polite">
          {isLoading ? null : (
            <>
              <strong>{clusters.length}</strong> cluster{clusters.length !== 1 ? 's' : ''} &middot;{' '}
              <strong>{totalDupes}</strong> redundant record{totalDupes !== 1 ? 's' : ''}
              {skippedNoKey > 0 && (
                <>
                  {' '}&middot;{' '}
                  <span className="text-yellow-700 dark:text-yellow-400">
                    {skippedNoKey} record{skippedNoKey !== 1 ? 's' : ''} skipped (no {key})
                  </span>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {lastFailures.length > 0 && (
        <div
          className="p-3 bg-red-50 dark:bg-red-900/20 rounded-md border border-red-200 dark:border-red-700/40"
          role="alert"
          aria-live="polite"
        >
          <div className="flex items-baseline justify-between">
            <p className="text-sm font-medium text-red-800 dark:text-red-300">
              {lastFailures.length} merge failure{lastFailures.length !== 1 ? 's' : ''}
            </p>
            <button
              type="button"
              onClick={() => setLastFailures([])}
              className="text-xs text-red-700 dark:text-red-400 hover:underline"
            >
              Dismiss
            </button>
          </div>
          <ul className="mt-1 space-y-0.5">
            {lastFailures.map((f) => (
              <li key={f.id} className="text-xs text-red-700 dark:text-red-400 flex items-center gap-2">
                <a
                  href={detailHref(entityType, f.id)}
                  className="font-mono underline hover:no-underline"
                >
                  #{f.id}
                </a>
                <span>{FAILURE_CODE_LABEL[f.reason_code]}</span>
                <span className="text-red-500 dark:text-red-500/80 truncate">{f.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : error ? (
        <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-md text-sm text-red-700 dark:text-red-300">
          Failed to load clusters: {error instanceof Error ? error.message : String(error)}
        </div>
      ) : clusters.length === 0 ? (
        <div className="text-center py-12 text-sm text-gray-500 dark:text-gray-400">
          No duplicate clusters found for {entityType} on {key}. Nothing to clean up here.
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {clusters.map((c) => (
            <ClusterCard
              key={`${c.key}:${c.key_value}`}
              entityType={entityType}
              cluster={c}
              busy={merge.isPending && pendingMerge?.cluster.key_value === c.key_value}
              onMerge={(winnerId, loserIds) =>
                setPendingMerge({ cluster: c, winnerId, loserIds })
              }
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        isOpen={pendingMerge !== null}
        title={`Merge ${pendingMerge?.loserIds.length ?? 0} record${(pendingMerge?.loserIds.length ?? 0) !== 1 ? 's' : ''}?`}
        message={
          pendingMerge
            ? `${pendingMerge.loserIds.length} ${entityType} record${pendingMerge.loserIds.length !== 1 ? 's' : ''} will be soft-deleted and every related activity, opportunity, quote, proposal, and contract will repoint to the winner. The losers stay reachable as merged tombstones for audit history but won't appear in list views. This action is recorded in the audit log.`
            : ''
        }
        confirmLabel="Merge"
        variant="warning"
        isLoading={merge.isPending}
        onConfirm={() => {
          if (pendingMerge) {
            merge.mutate({
              winnerId: pendingMerge.winnerId,
              loserIds: pendingMerge.loserIds,
            });
          }
        }}
        onClose={() => setPendingMerge(null)}
      />
    </div>
  );
}

/**
 * Admin page for browsing, bulk granting, and revoking EntityShare rows.
 * Accessible to admin role only.
 */

import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  LockClosedIcon,
  ShareIcon,
  UserPlusIcon,
} from '@heroicons/react/24/outline';

import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { Badge } from '../../components/ui/Badge';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { PaginationBar } from '../../components/ui/Pagination';
import { Select } from '../../components/ui/Select';
import { useAuthStore } from '../../store/authStore';
import { useUsers } from '../../hooks/useAuth';
import { usePageTitle } from '../../hooks/usePageTitle';
import { bulkShareAdmin, listAdminShares, revokeShare } from '../../api/sharing';
import type {
  AdminBulkShareResponse,
  AdminShareItem,
  PermissionLevel,
} from '../../api/sharing';
import { formatDate } from '../../utils/formatters';
import { showError, showSuccess, showWarning } from '../../utils/toast';

// ``quotes`` retired 2026-05-14 — quotes router unmounted. Historical
// EntityShare rows targeting quotes still exist in the DB but are no longer
// reachable from the admin browser filter. ``contracts`` retired the same day.
const ENTITY_TYPE_OPTIONS = [
  { value: '', label: 'All types' },
  { value: 'contacts', label: 'Contacts' },
  { value: 'companies', label: 'Companies' },
  { value: 'leads', label: 'Leads' },
  { value: 'proposals', label: 'Proposals' },
];

const BULK_ENTITY_TYPE_OPTIONS = ENTITY_TYPE_OPTIONS.filter((option) => option.value);

const PERMISSION_FILTER_OPTIONS = [
  { value: '', label: 'All permissions' },
  { value: 'view', label: 'View' },
  { value: 'edit', label: 'Edit' },
  { value: 'assignee', label: 'Assignee' },
];

const PERMISSION_GRANT_OPTIONS = [
  { value: 'view', label: 'View' },
  { value: 'edit', label: 'Edit' },
  { value: 'assignee', label: 'Assignee' },
];

const PERMISSION_BADGE: Record<string, 'blue' | 'yellow' | 'green'> = {
  view: 'blue',
  edit: 'yellow',
  assignee: 'green',
};

const PAGE_SIZE = 50;
const BULK_MAX = 500;

function entityDetailHref(entityType: string, entityId: number): string {
  const singular: Record<string, string> = {
    contacts: 'contacts',
    companies: 'companies',
    leads: 'leads',
    proposals: 'proposals',
  };
  const base = singular[entityType] ?? entityType;
  return `/${base}/${entityId}`;
}

function parseEntityIds(raw: string) {
  const invalid: string[] = [];
  const ids: number[] = [];
  const seen = new Set<number>();
  let tooMany = false;
  const tokens = raw.split(/[\s,]+/).map((token) => token.trim()).filter(Boolean);

  const addId = (id: number) => {
    if (seen.has(id)) return;
    if (ids.length >= BULK_MAX) {
      tooMany = true;
      return;
    }
    seen.add(id);
    ids.push(id);
  };

  for (const token of tokens) {
    const rangeMatch = token.match(/^(\d+)-(\d+)$/);
    if (rangeMatch) {
      const start = Number(rangeMatch[1]);
      const end = Number(rangeMatch[2]);
      if (
        start < 1 ||
        end < start ||
        !Number.isSafeInteger(start) ||
        !Number.isSafeInteger(end)
      ) {
        invalid.push(token);
        continue;
      }
      if (end - start + 1 > BULK_MAX) {
        tooMany = true;
        continue;
      }
      for (let id = start; id <= end; id += 1) {
        addId(id);
      }
      continue;
    }

    if (!/^\d+$/.test(token)) {
      invalid.push(token);
      continue;
    }

    const id = Number(token);
    if (id < 1 || !Number.isSafeInteger(id)) {
      invalid.push(token);
      continue;
    }
    addId(id);
  }

  return {
    ids,
    invalid,
    tooMany,
  };
}

function resultTone(result: AdminBulkShareResponse | null) {
  if (!result) return null;
  return result.failed > 0 ? 'warning' : 'success';
}

export default function AdminSharingPage() {
  usePageTitle('Sharing — Admin');

  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const queryClient = useQueryClient();

  const isAuthorized = user?.is_superuser || user?.role === 'admin';

  const [page, setPage] = useState(1);
  const [entityType, setEntityType] = useState('');
  const [sharedWithId, setSharedWithId] = useState('');
  const [sharedById, setSharedById] = useState('');
  const [permissionLevel, setPermissionLevel] = useState('');
  const [revokeTarget, setRevokeTarget] = useState<AdminShareItem | null>(null);

  const [bulkEntityType, setBulkEntityType] = useState('contacts');
  const [bulkSharedWithId, setBulkSharedWithId] = useState('');
  const [bulkPermission, setBulkPermission] = useState<PermissionLevel>('view');
  const [bulkRecordIds, setBulkRecordIds] = useState('');
  const [bulkResult, setBulkResult] = useState<AdminBulkShareResponse | null>(null);

  const { data: usersData } = useUsers(0, 200, { enabled: isAuthorized });

  const { data, isLoading } = useQuery({
    queryKey: [
      'admin',
      'shares',
      page,
      entityType,
      sharedWithId,
      sharedById,
      permissionLevel,
    ],
    queryFn: () =>
      listAdminShares({
        page,
        page_size: PAGE_SIZE,
        entity_type: entityType || undefined,
        shared_with_user_id: sharedWithId ? Number(sharedWithId) : undefined,
        shared_by_user_id: sharedById ? Number(sharedById) : undefined,
        permission_level: permissionLevel || undefined,
      }),
    enabled: isAuthorized,
  });

  const revokeMutation = useMutation({
    mutationFn: (shareId: number) => revokeShare(shareId),
    onSuccess: () => {
      showSuccess('Share revoked');
      setRevokeTarget(null);
      queryClient.invalidateQueries({ queryKey: ['admin', 'shares'] });
    },
    onError: () => {
      showError('Failed to revoke share');
    },
  });

  const parsedBulkIds = useMemo(() => parseEntityIds(bulkRecordIds), [bulkRecordIds]);

  const bulkMutation = useMutation({
    mutationFn: () =>
      bulkShareAdmin({
        entity_type: bulkEntityType,
        entity_ids: parsedBulkIds.ids,
        shared_with_user_id: Number(bulkSharedWithId),
        permission_level: bulkPermission,
      }),
    onSuccess: (result) => {
      setBulkResult(result);
      queryClient.invalidateQueries({ queryKey: ['admin', 'shares'] });
      if (result.failed > 0) {
        const noun = result.failed === 1 ? 'ID' : 'IDs';
        showWarning(`Bulk sharing finished with ${result.failed} failed ${noun}`);
      } else {
        showSuccess('Bulk sharing complete');
      }
    },
    onError: () => {
      showError('Failed to bulk share records');
    },
  });

  const users = usersData ?? [];
  const userOptions = [
    { value: '', label: 'Any user' },
    ...users.map((u) => ({
      value: String(u.id),
      label: `${u.full_name} (${u.email})`,
    })),
  ];
  const teammateOptions = [
    { value: '', label: 'Select teammate' },
    ...users
      .filter((u) => u.id !== user?.id)
      .map((u) => ({
        value: String(u.id),
        label: `${u.full_name} (${u.email})`,
      })),
  ];

  function handleFilterChange() {
    setPage(1);
  }

  function handleBulkSubmit() {
    if (
      !bulkSharedWithId ||
      parsedBulkIds.ids.length === 0 ||
      parsedBulkIds.invalid.length > 0 ||
      parsedBulkIds.tooMany
    ) {
      return;
    }
    bulkMutation.mutate();
  }

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
          Only admins can view this page.
        </p>
        <Button variant="secondary" className="mt-6" onClick={() => navigate('/')}>
          Go to Dashboard
        </Button>
      </div>
    );
  }

  const total = data?.total ?? 0;
  const pages = Math.ceil(total / PAGE_SIZE);
  const bulkCanSubmit =
    Boolean(bulkSharedWithId) &&
    parsedBulkIds.ids.length > 0 &&
    parsedBulkIds.invalid.length === 0 &&
    !parsedBulkIds.tooMany &&
    !bulkMutation.isPending;
  const failedIds =
    bulkResult?.items
      .filter((item) => item.status === 'failed')
      .map((item) => item.entity_id)
      .join(', ') ?? '';
  const bulkTone = resultTone(bulkResult);

  return (
    <div className="space-y-6" data-guide="admin-sharing-page">
      <div className="flex items-center gap-3">
        <ShareIcon className="h-6 w-6 text-gray-500 dark:text-gray-400" aria-hidden="true" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Sharing</h1>
          <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
            Grant teammate access and audit every record share.
          </p>
        </div>
      </div>

      <div data-guide="admin-sharing-bulk-add">
        <Card>
          <CardHeader
            title="Bulk add access"
            description="Grant one teammate access to up to 500 records at once."
            action={
              <Badge variant={parsedBulkIds.ids.length > 0 ? 'blue' : 'gray'} size="sm">
                {parsedBulkIds.ids.length} selected
              </Badge>
            }
          />
          <CardBody>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
              <Select
                id="bulk-entity-type"
                label="Record type"
                value={bulkEntityType}
                onChange={(event) => {
                  setBulkEntityType(event.target.value);
                  setBulkResult(null);
                }}
                options={BULK_ENTITY_TYPE_OPTIONS}
              />
              <Select
                id="bulk-shared-with"
                label="Teammate"
                value={bulkSharedWithId}
                onChange={(event) => {
                  setBulkSharedWithId(event.target.value);
                  setBulkResult(null);
                }}
                options={teammateOptions}
              />
              <Select
                id="bulk-permission"
                label="Permission"
                value={bulkPermission}
                onChange={(event) => {
                  setBulkPermission(event.target.value as PermissionLevel);
                  setBulkResult(null);
                }}
                options={PERMISSION_GRANT_OPTIONS}
              />
              <div className="flex items-end">
                <Button
                  type="button"
                  fullWidth
                  onClick={handleBulkSubmit}
                  disabled={!bulkCanSubmit}
                  isLoading={bulkMutation.isPending}
                  leftIcon={<UserPlusIcon className="h-5 w-5" aria-hidden="true" />}
                >
                  Apply
                </Button>
              </div>
            </div>

            <div className="mt-4">
              <label
                htmlFor="bulk-record-ids"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Record IDs
              </label>
              <textarea
                id="bulk-record-ids"
                value={bulkRecordIds}
                onChange={(event) => {
                  setBulkRecordIds(event.target.value);
                  setBulkResult(null);
                }}
                rows={4}
                placeholder="42, 43, 44 or 100-120"
                className="mt-1 block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm transition-colors focus-visible:border-primary-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                aria-describedby="bulk-record-ids-status"
              />
              <div
                id="bulk-record-ids-status"
                className="mt-2 min-h-5 text-xs text-gray-500 dark:text-gray-400"
              >
                {parsedBulkIds.invalid.length > 0 ? (
                  <span className="text-red-600 dark:text-red-400">
                    Invalid: {parsedBulkIds.invalid.join(', ')}
                  </span>
                ) : parsedBulkIds.tooMany ? (
                  <span className="text-red-600 dark:text-red-400">
                    Limit is {BULK_MAX} records.
                  </span>
                ) : (
                  <span>{parsedBulkIds.ids.length} unique record ID(s)</span>
                )}
              </div>
            </div>

            {bulkResult && (
              <div
                className={`mt-4 rounded-lg border p-4 ${
                  bulkTone === 'warning'
                    ? 'border-yellow-200 bg-yellow-50 text-yellow-900 dark:border-yellow-900/40 dark:bg-yellow-900/20 dark:text-yellow-100'
                    : 'border-green-200 bg-green-50 text-green-900 dark:border-green-900/40 dark:bg-green-900/20 dark:text-green-100'
                }`}
                role="status"
              >
                <div className="flex items-start gap-3">
                  {bulkTone === 'warning' ? (
                    <ExclamationTriangleIcon className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
                  ) : (
                    <CheckCircleIcon className="mt-0.5 h-5 w-5 flex-shrink-0" aria-hidden="true" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold">
                      {bulkTone === 'warning'
                        ? 'Bulk sharing finished with issues'
                        : 'Bulk sharing complete'}
                    </p>
                    <p className="mt-1 text-sm">
                      Created {bulkResult.created}, updated {bulkResult.updated}, skipped{' '}
                      {bulkResult.skipped}, failed {bulkResult.failed}.
                    </p>
                    {failedIds && <p className="mt-1 text-sm">Failed IDs: {failedIds}</p>}
                  </div>
                </div>
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      <div data-guide="admin-sharing-filters">
        <Card>
          <CardBody className="!mt-0">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <label
                  htmlFor="filter-entity-type"
                  className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400"
                >
                  Entity type
                </label>
                <Select
                  id="filter-entity-type"
                  value={entityType}
                  onChange={(event) => {
                    setEntityType(event.target.value);
                    handleFilterChange();
                  }}
                  options={ENTITY_TYPE_OPTIONS}
                />
              </div>

              <div>
                <label
                  htmlFor="filter-shared-with"
                  className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400"
                >
                  Shared with
                </label>
                <Select
                  id="filter-shared-with"
                  value={sharedWithId}
                  onChange={(event) => {
                    setSharedWithId(event.target.value);
                    handleFilterChange();
                  }}
                  options={userOptions}
                />
              </div>

              <div>
                <label
                  htmlFor="filter-shared-by"
                  className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400"
                >
                  Shared by
                </label>
                <Select
                  id="filter-shared-by"
                  value={sharedById}
                  onChange={(event) => {
                    setSharedById(event.target.value);
                    handleFilterChange();
                  }}
                  options={userOptions}
                />
              </div>

              <div>
                <label
                  htmlFor="filter-permission"
                  className="mb-1 block text-xs font-medium text-gray-500 dark:text-gray-400"
                >
                  Permission
                </label>
                <Select
                  id="filter-permission"
                  value={permissionLevel}
                  onChange={(event) => {
                    setPermissionLevel(event.target.value);
                    handleFilterChange();
                  }}
                  options={PERMISSION_FILTER_OPTIONS}
                />
              </div>
            </div>
          </CardBody>
        </Card>
      </div>

      <div data-guide="admin-sharing-table">
        <Card>
          <CardHeader
            title={`Shares (${total.toLocaleString()})`}
            description="Click Revoke to remove a share immediately."
          />
          <CardBody className="!mt-0">
            {isLoading ? (
              <div className="flex justify-center py-12">
                <Spinner />
              </div>
            ) : !data || data.items.length === 0 ? (
              <p className="px-6 py-8 text-sm text-gray-500 dark:text-gray-400">
                No shares match the current filters.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="bg-gray-50 dark:bg-gray-800/50">
                    <tr>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400"
                      >
                        Entity
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400"
                      >
                        Shared with
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400"
                      >
                        Shared by
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400"
                      >
                        Permission
                      </th>
                      <th
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400"
                      >
                        Created
                      </th>
                      <th scope="col" className="px-4 py-3 text-right">
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white dark:divide-gray-700 dark:bg-gray-800">
                    {data.items.map((item) => (
                      <tr
                        key={item.id}
                        className="hover:bg-gray-50 dark:hover:bg-gray-700/40"
                      >
                        <td className="whitespace-nowrap px-4 py-3">
                          <a
                            href={entityDetailHref(item.entity_type, item.entity_id)}
                            className="text-sm font-medium text-primary-600 hover:underline dark:text-primary-400"
                          >
                            {item.entity_type} #{item.entity_id}
                          </a>
                        </td>
                        <td className="px-4 py-3">
                          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                            {item.shared_with_user_name}
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            {item.shared_with_user_email}
                          </p>
                        </td>
                        <td className="px-4 py-3">
                          <p className="text-sm text-gray-900 dark:text-gray-100">
                            {item.shared_by_user_name}
                          </p>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3">
                          <Badge
                            variant={PERMISSION_BADGE[item.permission_level] ?? 'gray'}
                            size="sm"
                          >
                            {item.permission_level}
                          </Badge>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                          {formatDate(item.created_at)}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right">
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => setRevokeTarget(item)}
                          >
                            Revoke
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {pages > 1 && (
              <PaginationBar
                page={page}
                pages={pages}
                total={total}
                pageSize={PAGE_SIZE}
                onPageChange={setPage}
              />
            )}
          </CardBody>
        </Card>
      </div>

      <ConfirmDialog
        isOpen={revokeTarget !== null}
        onClose={() => setRevokeTarget(null)}
        onConfirm={() => {
          if (revokeTarget) revokeMutation.mutate(revokeTarget.id);
        }}
        title="Revoke this share?"
        message={
          revokeTarget
            ? `This will immediately remove ${revokeTarget.shared_with_user_name}'s access to ${revokeTarget.entity_type} #${revokeTarget.entity_id}.`
            : ''
        }
        confirmLabel="Revoke"
        variant="danger"
        isLoading={revokeMutation.isPending}
      />
    </div>
  );
}

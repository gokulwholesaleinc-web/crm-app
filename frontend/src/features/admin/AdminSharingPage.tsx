/**
 * Admin page for browsing, filtering, and revoking EntityShare rows.
 * Accessible to admin/manager roles only.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { showSuccess, showError } from '../../utils/toast';
import {
  LockClosedIcon,
  ShareIcon,
} from '@heroicons/react/24/outline';

import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { Badge } from '../../components/ui/Badge';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { PaginationBar } from '../../components/ui/Pagination';
import { Select } from '../../components/ui/Select';
import { useAuthStore } from '../../store/authStore';
import { usePageTitle } from '../../hooks/usePageTitle';
import { listAdminShares, revokeShare } from '../../api/sharing';
import { getAdminUsers } from '../../api/admin';
import type { AdminShareItem } from '../../api/sharing';
import type { AdminUser } from '../../types';
import { formatDate } from '../../utils/formatters';

// ``quotes`` retired 2026-05-14 — quotes router unmounted. Historical
// EntityShare rows targeting quotes still exist in the DB but are
// no longer reachable from the admin browser filter.
const ENTITY_TYPE_OPTIONS = [
  { value: '', label: 'All types' },
  { value: 'contacts', label: 'Contacts' },
  { value: 'companies', label: 'Companies' },
  { value: 'leads', label: 'Leads' },
  { value: 'proposals', label: 'Proposals' },
  { value: 'contracts', label: 'Contracts' },
];

const PERMISSION_OPTIONS = [
  { value: '', label: 'All permissions' },
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

function EntityDetailHref(entityType: string, entityId: number): string {
  const singular: Record<string, string> = {
    contacts: 'contacts',
    companies: 'companies',
    leads: 'leads',
    proposals: 'proposals',
    contracts: 'contracts',
  };
  const base = singular[entityType] ?? entityType;
  return `/${base}/${entityId}`;
}

export default function AdminSharingPage() {
  usePageTitle('Sharing — Admin');

  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const queryClient = useQueryClient();

  const isAuthorized =
    user?.is_superuser || user?.role === 'admin' || user?.role === 'manager';

  const [page, setPage] = useState(1);
  const [entityType, setEntityType] = useState('');
  const [sharedWithId, setSharedWithId] = useState('');
  const [sharedById, setSharedById] = useState('');
  const [permissionLevel, setPermissionLevel] = useState('');
  const [revokeTarget, setRevokeTarget] = useState<AdminShareItem | null>(null);

  const { data: usersData } = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: getAdminUsers,
    enabled: isAuthorized,
  });

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

  const users: AdminUser[] = usersData ?? [];
  const userOptions = [
    { value: '', label: 'Any user' },
    ...users.map((u) => ({
      value: String(u.id),
      label: `${u.full_name} (${u.email})`,
    })),
  ];

  function handleFilterChange() {
    setPage(1);
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
          Only admins and managers can view this page.
        </p>
        <Button variant="secondary" className="mt-6" onClick={() => navigate('/')}>
          Go to Dashboard
        </Button>
      </div>
    );
  }

  const total = data?.total ?? 0;
  const pages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <ShareIcon className="h-6 w-6 text-gray-500 dark:text-gray-400" aria-hidden="true" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Sharing</h1>
          <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
            All record shares across the system
          </p>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <CardBody>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label
                htmlFor="filter-entity-type"
                className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
              >
                Entity type
              </label>
              <Select
                id="filter-entity-type"
                value={entityType}
                onChange={(e) => {
                  setEntityType(e.target.value);
                  handleFilterChange();
                }}
                options={ENTITY_TYPE_OPTIONS}
              />
            </div>

            <div>
              <label
                htmlFor="filter-shared-with"
                className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
              >
                Shared with
              </label>
              <Select
                id="filter-shared-with"
                value={sharedWithId}
                onChange={(e) => {
                  setSharedWithId(e.target.value);
                  handleFilterChange();
                }}
                options={userOptions}
              />
            </div>

            <div>
              <label
                htmlFor="filter-shared-by"
                className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
              >
                Shared by
              </label>
              <Select
                id="filter-shared-by"
                value={sharedById}
                onChange={(e) => {
                  setSharedById(e.target.value);
                  handleFilterChange();
                }}
                options={userOptions}
              />
            </div>

            <div>
              <label
                htmlFor="filter-permission"
                className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
              >
                Permission
              </label>
              <Select
                id="filter-permission"
                value={permissionLevel}
                onChange={(e) => {
                  setPermissionLevel(e.target.value);
                  handleFilterChange();
                }}
                options={PERMISSION_OPTIONS}
              />
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Table */}
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
                      className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Entity
                    </th>
                    <th
                      scope="col"
                      className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Shared with
                    </th>
                    <th
                      scope="col"
                      className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Shared by
                    </th>
                    <th
                      scope="col"
                      className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Permission
                    </th>
                    <th
                      scope="col"
                      className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Created
                    </th>
                    <th scope="col" className="px-4 py-3 text-right">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {data.items.map((item) => (
                    <tr
                      key={item.id}
                      className="hover:bg-gray-50 dark:hover:bg-gray-700/40"
                    >
                      <td className="px-4 py-3 whitespace-nowrap">
                        <a
                          href={EntityDetailHref(item.entity_type, item.entity_id)}
                          className="text-sm font-medium text-primary-600 dark:text-primary-400 hover:underline"
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
                      <td className="px-4 py-3 whitespace-nowrap">
                        <Badge
                          variant={PERMISSION_BADGE[item.permission_level] ?? 'gray'}
                          size="sm"
                        >
                          {item.permission_level}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(item.created_at)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-right">
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

      {/* Revoke confirm dialog */}
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

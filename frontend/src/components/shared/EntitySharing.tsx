import { useState } from 'react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { SearchableSelect } from '../ui/SearchableSelect';
import { Spinner } from '../ui/Spinner';
import { useEntityShares, useShareEntity, useRevokeShare } from '../../hooks/useSharing';
import { useUsers } from '../../hooks/useAuth';
import type { PermissionLevel } from '../../api/sharing';
import { showSuccess } from '../../utils/toast';
import {
  KeyIcon,
  ShareIcon,
  ShieldCheckIcon,
  TrashIcon,
  UserCircleIcon,
  UserPlusIcon,
  UsersIcon,
} from '@heroicons/react/24/outline';

// ``quotes`` dropped from the union 2026-05-14 — quotes router unmounted.
// ``contracts`` dropped from the union 2026-05-14 — contracts router
// unmounted; contract terms now fold into the Proposal T&C inline.
export interface EntitySharingProps {
  entityType:
    | 'contacts'
    | 'companies'
    | 'leads'
    | 'proposals'
    | 'campaigns';
  entityId: number;
  ownerName?: string;
  canManage: boolean;
}

const PERMISSION_OPTIONS: { value: PermissionLevel; label: string; helper: string }[] = [
  {
    value: 'view',
    label: 'Can view',
    helper: 'Good for read-only collaboration and visibility.',
  },
  {
    value: 'edit',
    label: 'Can edit',
    helper: 'Use when a teammate should help maintain this record.',
  },
  {
    value: 'assignee',
    label: 'Assignee',
    helper: 'Use when a teammate is actively responsible for this record.',
  },
];

function permissionLabel(level: string): string {
  return PERMISSION_OPTIONS.find((option) => option.value === level)?.label ?? level;
}

function permissionHelper(level: PermissionLevel): string {
  return PERMISSION_OPTIONS.find((option) => option.value === level)?.helper ?? '';
}

function permissionBadgeVariant(level: string): 'gray' | 'blue' | 'indigo' {
  if (level === 'edit') return 'blue';
  if (level === 'assignee') return 'indigo';
  return 'gray';
}

export function EntitySharing({
  entityType,
  entityId,
  ownerName,
  canManage,
}: EntitySharingProps) {
  const {
    data: sharesData,
    isLoading,
    isError: sharesFetchFailed,
    refetch: refetchShares,
  } = useEntityShares(entityType, entityId);
  const { data: users } = useUsers();
  const shareMutation = useShareEntity();
  const revokeMutation = useRevokeShare();

  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [permission, setPermission] = useState<PermissionLevel>('view');
  const [showForm, setShowForm] = useState(false);

  const shares = sharesData?.items ?? [];
  const shareCount = shares.length;
  const sharedUserIds = new Set(shares.map((share) => share.shared_with_user_id));
  const availableUsers =
    users
      ?.filter((user) => !sharedUserIds.has(user.id))
      .map((user) => ({ value: user.id, label: `${user.full_name} (${user.email})` })) ?? [];
  const strongestAccess =
    shares.some((share) => share.permission_level === 'assignee')
      ? 'Assignee'
      : shares.some((share) => share.permission_level === 'edit')
        ? 'Edit'
        : shareCount > 0
          ? 'View'
          : 'Private';

  const handleShare = async () => {
    if (!selectedUserId) return;
    try {
      await shareMutation.mutateAsync({
        entity_type: entityType,
        entity_id: entityId,
        shared_with_user_id: selectedUserId,
        permission_level: permission,
      });
      setSelectedUserId(null);
      setShowForm(false);
      showSuccess('Record shared');
    } catch {
      // Toast surfaces via the mutation's onError handler.
    }
  };

  const handleRevoke = (shareId: number) => {
    revokeMutation.mutate({
      shareId,
      entityType,
      entityId,
    });
  };

  return (
    <section className="rounded-lg border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div className="border-b border-gray-100 px-4 py-4 dark:border-gray-700 sm:px-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <span className="inline-flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-300">
              <ShareIcon className="h-5 w-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                Sharing
              </h3>
              <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
                {shareCount > 0
                  ? `Shared with ${shareCount} ${shareCount === 1 ? 'person' : 'people'}`
                  : 'Private record'}
              </p>
            </div>
          </div>
          {canManage && (
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<UserPlusIcon className="h-4 w-4" aria-hidden="true" />}
              onClick={() => setShowForm((visible) => !visible)}
            >
              Share
            </Button>
          )}
        </div>
      </div>

      <div className="space-y-5 px-4 py-5 sm:px-6">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-3 dark:border-gray-700 dark:bg-gray-900/30">
            <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              <UserCircleIcon className="h-4 w-4" aria-hidden="true" />
              Owner
            </div>
            <p className="mt-2 truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
              {ownerName || 'Unassigned'}
            </p>
          </div>
          <div className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-3 dark:border-gray-700 dark:bg-gray-900/30">
            <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              <UsersIcon className="h-4 w-4" aria-hidden="true" />
              Shared access
            </div>
            <p className="mt-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
              {shareCount} {shareCount === 1 ? 'teammate' : 'teammates'}
            </p>
          </div>
          <div className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-3 dark:border-gray-700 dark:bg-gray-900/30">
            <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              <KeyIcon className="h-4 w-4" aria-hidden="true" />
              Access level
            </div>
            <p className="mt-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
              {strongestAccess}
            </p>
          </div>
        </div>

        {canManage && showForm && (
          <div className="rounded-lg border border-primary-100 bg-primary-50/50 p-4 dark:border-primary-900/40 dark:bg-primary-900/10">
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
              <SearchableSelect
                label="Teammate"
                id="entity-sharing-user"
                value={selectedUserId}
                onChange={setSelectedUserId}
                options={availableUsers}
                placeholder={
                  availableUsers.length > 0 ? 'Search users...' : 'No available users'
                }
              />
              <div>
                <label
                  htmlFor="entity-sharing-permission"
                  className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
                >
                  Permission
                </label>
                <select
                  id="entity-sharing-permission"
                  value={permission}
                  onChange={(event) => setPermission(event.target.value as PermissionLevel)}
                  className="block w-full rounded-lg border border-gray-300 bg-white py-2 pl-3 pr-8 text-sm text-gray-900 shadow-sm focus-visible:border-primary-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100"
                >
                  {PERMISSION_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
                <ShieldCheckIcon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                {permissionHelper(permission)}
              </p>
              <div className="flex justify-end gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    setShowForm(false);
                    setSelectedUserId(null);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleShare}
                  disabled={!selectedUserId || shareMutation.isPending}
                  isLoading={shareMutation.isPending}
                >
                  Share
                </Button>
              </div>
            </div>
          </div>
        )}

        <div>
          <div className="mb-2 flex items-center justify-between">
            <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Teammates with access
            </h4>
            {shareCount > 0 && (
              <Badge variant="blue" size="sm">
                {shareCount} shared
              </Badge>
            )}
          </div>

          {isLoading ? (
            <div className="flex justify-center py-6">
              <Spinner size="sm" />
            </div>
          ) : sharesFetchFailed ? (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-900/20 dark:text-red-300"
            >
              <p>Failed to load sharing for this record.</p>
              <button
                type="button"
                onClick={() => void refetchShares()}
                className="mt-2 text-xs font-medium underline hover:no-underline"
              >
                Retry
              </button>
            </div>
          ) : shares.length === 0 ? (
            <p className="rounded-lg border border-dashed border-gray-200 px-4 py-6 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
              Not shared yet.
            </p>
          ) : (
            <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100 dark:divide-gray-700 dark:border-gray-700">
              {shares.map((share) => {
                const sharedUser = users?.find((user) => user.id === share.shared_with_user_id);
                return (
                  <li key={share.id} className="flex items-center justify-between gap-3 px-3 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
                        {sharedUser?.full_name ?? `User #${share.shared_with_user_id}`}
                      </p>
                      {sharedUser?.email && (
                        <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                          {sharedUser.email}
                        </p>
                      )}
                    </div>
                    <Badge
                      variant={permissionBadgeVariant(share.permission_level)}
                      size="sm"
                    >
                      {permissionLabel(share.permission_level)}
                    </Badge>
                    {canManage && (
                      <button
                        type="button"
                        onClick={() => handleRevoke(share.id)}
                        className="rounded p-1 text-gray-400 transition-colors hover:text-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                        title="Revoke access"
                        aria-label={`Revoke access for ${sharedUser?.full_name ?? `user ${share.shared_with_user_id}`}`}
                        disabled={revokeMutation.isPending}
                      >
                        <TrashIcon className="h-4 w-4" aria-hidden="true" />
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}

export default EntitySharing;

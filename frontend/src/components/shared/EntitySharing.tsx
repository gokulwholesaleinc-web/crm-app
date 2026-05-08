import { useState } from 'react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { SearchableSelect } from '../ui/SearchableSelect';
import { Spinner } from '../ui/Spinner';
import { useEntityShares, useShareEntity, useRevokeShare } from '../../hooks/useSharing';
import { useUsers } from '../../hooks/useAuth';
import type { PermissionLevel } from '../../api/sharing';
import {
  ShareIcon,
  TrashIcon,
  UserPlusIcon,
  UserCircleIcon,
} from '@heroicons/react/24/outline';

export interface EntitySharingProps {
  entityType:
    | 'contacts'
    | 'companies'
    | 'leads'
    | 'opportunities'
    | 'quotes'
    | 'proposals'
    | 'contracts'
    | 'campaigns';
  entityId: number;
  ownerName?: string;
  canManage: boolean;
}

const PERMISSION_OPTIONS: { value: PermissionLevel; label: string }[] = [
  { value: 'view', label: 'Can view' },
  { value: 'edit', label: 'Can edit' },
  { value: 'assignee', label: 'Assignee' },
];

function permissionLabel(level: string): string {
  return PERMISSION_OPTIONS.find((o) => o.value === level)?.label ?? level;
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
  const { data: sharesData, isLoading } = useEntityShares(entityType, entityId);
  const { data: users } = useUsers();
  const shareMutation = useShareEntity();
  const revokeMutation = useRevokeShare();

  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const [permission, setPermission] = useState<PermissionLevel>('view');
  const [showForm, setShowForm] = useState(false);

  const shares = sharesData?.items ?? [];
  const shareCount = shares.length;

  // Users not already shared with
  const sharedUserIds = new Set(shares.map((s) => s.shared_with_user_id));
  const availableUsers =
    users
      ?.filter((u) => !sharedUserIds.has(u.id))
      .map((u) => ({ value: u.id, label: `${u.full_name} (${u.email})` })) ?? [];

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
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-transparent dark:border-gray-700">
      <div className="px-4 py-5 sm:p-6">
        {/* Header row */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <ShareIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
            <h3 className="text-base font-medium text-gray-900 dark:text-gray-100">
              Sharing
            </h3>
            {shareCount > 0 && (
              <Badge variant="blue" size="sm">
                Shared with {shareCount} {shareCount === 1 ? 'person' : 'people'}
              </Badge>
            )}
          </div>
          {canManage && (
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<UserPlusIcon className="h-4 w-4" aria-hidden="true" />}
              onClick={() => setShowForm((v) => !v)}
            >
              Share
            </Button>
          )}
        </div>

        {/* Owner row */}
        {ownerName && (
          <div className="flex items-center gap-2 mb-3 pb-3 border-b border-gray-100 dark:border-gray-700">
            <UserCircleIcon className="h-4 w-4 text-gray-400 flex-shrink-0" aria-hidden="true" />
            <span className="text-sm text-gray-500 dark:text-gray-400">Owner:</span>
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{ownerName}</span>
            <Badge variant="gray" size="sm">Owner</Badge>
          </div>
        )}

        {/* Add-share form */}
        {canManage && showForm && (
          <div className="mb-4 p-3 bg-gray-50 dark:bg-gray-700 rounded-lg space-y-3">
            <SearchableSelect
              label="User"
              id="entity-sharing-user"
              value={selectedUserId}
              onChange={setSelectedUserId}
              options={availableUsers}
              placeholder="Search users..."
            />
            <div>
              <label
                htmlFor="entity-sharing-permission"
                className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
              >
                Permission
              </label>
              <select
                id="entity-sharing-permission"
                value={permission}
                onChange={(e) => setPermission(e.target.value as PermissionLevel)}
                className="block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500 text-sm bg-white dark:bg-gray-600 dark:text-gray-100 py-2 pl-3 pr-8"
              >
                {PERMISSION_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
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
        )}

        {/* Shares list */}
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Spinner size="sm" />
          </div>
        ) : shares.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
            Not shared yet.
          </p>
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-gray-700">
            {shares.map((share) => {
              const sharedUser = users?.find((u) => u.id === share.shared_with_user_id);
              return (
                <li key={share.id} className="flex items-center justify-between py-3 gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {sharedUser?.full_name ?? `User #${share.shared_with_user_id}`}
                    </p>
                    {sharedUser?.email && (
                      <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
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
                      className="p-1 text-gray-400 hover:text-red-500 transition-colors rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
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
  );
}

export default EntitySharing;

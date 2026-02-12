/**
 * SharePanel - allows sharing an entity with other users.
 * Shows current shares and allows adding/removing.
 */

import { useState } from 'react';
import { Button } from '../ui/Button';
import { Spinner } from '../ui/Spinner';
import { useEntityShares, useShareEntity, useRevokeShare } from '../../hooks/useSharing';
import { useUsers } from '../../hooks/useAuth';
import {
  ShareIcon,
  TrashIcon,
  UserPlusIcon,
} from '@heroicons/react/24/outline';

interface SharePanelProps {
  entityType: string;
  entityId: number;
}

function SharePanel({ entityType, entityId }: SharePanelProps) {
  const { data: sharesData, isLoading } = useEntityShares(entityType, entityId);
  const { data: users } = useUsers();
  const shareMutation = useShareEntity();
  const revokeMutation = useRevokeShare();

  const [selectedUserId, setSelectedUserId] = useState<number>(0);
  const [permission, setPermission] = useState<'view' | 'edit'>('view');
  const [showForm, setShowForm] = useState(false);

  const shares = sharesData?.items || [];

  const handleShare = async () => {
    if (!selectedUserId) return;
    await shareMutation.mutateAsync({
      entity_type: entityType,
      entity_id: entityId,
      shared_with_user_id: selectedUserId,
      permission_level: permission,
    });
    setSelectedUserId(0);
    setShowForm(false);
  };

  const handleRevoke = async (shareId: number) => {
    await revokeMutation.mutateAsync({
      shareId,
      entityType,
      entityId,
    });
  };

  // Filter out users that are already shared with
  const sharedUserIds = new Set(shares.map((s) => s.shared_with_user_id));
  const availableUsers = users?.filter((u) => !sharedUserIds.has(u.id)) || [];

  return (
    <div className="bg-white shadow rounded-lg">
      <div className="px-4 py-5 sm:p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <ShareIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
            <h3 className="text-base font-medium text-gray-900">Shared With</h3>
          </div>
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<UserPlusIcon className="h-4 w-4" />}
            onClick={() => setShowForm(!showForm)}
          >
            Share
          </Button>
        </div>

        {/* Share form */}
        {showForm && (
          <div className="mb-4 p-3 bg-gray-50 rounded-lg space-y-3">
            <div>
              <label htmlFor="share-user" className="block text-sm font-medium text-gray-700 mb-1">
                User
              </label>
              <select
                id="share-user"
                value={selectedUserId}
                onChange={(e) => setSelectedUserId(Number(e.target.value))}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
              >
                <option value={0}>Select a user...</option>
                {availableUsers.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name} ({u.email})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="share-permission" className="block text-sm font-medium text-gray-700 mb-1">
                Permission
              </label>
              <select
                id="share-permission"
                value={permission}
                onChange={(e) => setPermission(e.target.value as 'view' | 'edit')}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
              >
                <option value="view">View</option>
                <option value="edit">Edit</option>
              </select>
            </div>
            <div className="flex justify-end gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowForm(false)}
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
          <p className="text-sm text-gray-500 text-center py-4">
            Not shared with anyone yet.
          </p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {shares.map((share) => {
              const sharedUser = users?.find((u) => u.id === share.shared_with_user_id);
              return (
                <li key={share.id} className="flex items-center justify-between py-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {sharedUser?.full_name || `User #${share.shared_with_user_id}`}
                    </p>
                    <p className="text-xs text-gray-500">
                      {share.permission_level === 'edit' ? 'Can edit' : 'Can view'}
                    </p>
                  </div>
                  <button
                    onClick={() => handleRevoke(share.id)}
                    className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                    title="Revoke access"
                    disabled={revokeMutation.isPending}
                  >
                    <TrashIcon className="h-4 w-4" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

export default SharePanel;

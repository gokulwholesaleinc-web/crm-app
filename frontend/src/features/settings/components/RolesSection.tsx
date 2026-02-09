/**
 * Roles management section for the Settings page.
 * Shows current user's role and allows admins to manage roles.
 */

import { useState } from 'react';
import { useRoles, useMyPermissions, useAssignRole } from '../../../hooks/usePermissions';
import { useUsers } from '../../../hooks/useAuth';
import { useAuthStore } from '../../../store/authStore';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Spinner } from '../../../components/ui/Spinner';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { Modal, ModalFooter } from '../../../components/ui/Modal';
import {
  ShieldCheckIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline';
import type { BadgeVariant } from '../../../components/ui/Badge';

const ROLE_BADGE_COLORS: Record<string, BadgeVariant> = {
  admin: 'red',
  manager: 'purple',
  sales_rep: 'blue',
  viewer: 'gray',
};

const ROLE_LABELS: Record<string, string> = {
  admin: 'Admin',
  manager: 'Manager',
  sales_rep: 'Sales Rep',
  viewer: 'Viewer',
};

function formatPermissions(permissions: Record<string, string[]>): string[] {
  const lines: string[] = [];
  for (const [entity, actions] of Object.entries(permissions)) {
    if (actions.length > 0) {
      lines.push(`${entity}: ${actions.join(', ')}`);
    }
  }
  return lines;
}

export function RolesSection() {
  const { user } = useAuthStore();
  const { data: roles, isLoading: rolesLoading } = useRoles();
  const { data: myPermissions, isLoading: permsLoading } = useMyPermissions();
  const { data: users } = useUsers();
  const assignMutation = useAssignRole();
  const [assignModalOpen, setAssignModalOpen] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState<number>(0);
  const [selectedRoleId, setSelectedRoleId] = useState<number>(0);

  const isAdmin = user?.is_superuser || myPermissions?.role === 'admin';
  const isLoading = rolesLoading || permsLoading;

  const handleAssign = async () => {
    if (selectedUserId && selectedRoleId) {
      await assignMutation.mutateAsync({
        user_id: selectedUserId,
        role_id: selectedRoleId,
      });
      setAssignModalOpen(false);
      setSelectedUserId(0);
      setSelectedRoleId(0);
    }
  };

  return (
    <Card>
      <CardHeader
        title="Roles & Permissions"
        description="View your role and permissions"
        action={
          isAdmin ? (
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<UserGroupIcon className="h-4 w-4" />}
              onClick={() => setAssignModalOpen(true)}
            >
              Assign Role
            </Button>
          ) : undefined
        }
      />
      <CardBody className="p-4 sm:p-6">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Spinner size="md" />
          </div>
        ) : (
          <div className="space-y-6">
            {/* Current User Role */}
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-indigo-100 flex items-center justify-center">
                <ShieldCheckIcon className="h-5 w-5 text-indigo-600" />
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900">Your Role</p>
                <Badge variant={ROLE_BADGE_COLORS[myPermissions?.role ?? 'sales_rep'] ?? 'gray'}>
                  {ROLE_LABELS[myPermissions?.role ?? 'sales_rep'] ?? myPermissions?.role ?? 'Sales Rep'}
                </Badge>
              </div>
            </div>

            {/* Permissions Summary */}
            {myPermissions && (
              <div>
                <p className="text-sm font-medium text-gray-700 mb-2">Your Permissions</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {formatPermissions(myPermissions.permissions).map((line) => (
                    <div key={line} className="text-xs text-gray-600 bg-gray-50 rounded px-3 py-2">
                      {line}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* All Roles (visible to everyone) */}
            {roles && roles.length > 0 && (
              <div>
                <p className="text-sm font-medium text-gray-700 mb-2">Available Roles</p>
                <div className="flex flex-wrap gap-2">
                  {roles.map((role) => (
                    <Badge
                      key={role.id}
                      variant={ROLE_BADGE_COLORS[role.name] ?? 'gray'}
                      size="lg"
                    >
                      {ROLE_LABELS[role.name] ?? role.name}
                      {role.description ? ` - ${role.description}` : ''}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardBody>

      {/* Assign Role Modal (Admin only) */}
      <Modal
        isOpen={assignModalOpen}
        onClose={() => setAssignModalOpen(false)}
        title="Assign Role to User"
        size="md"
      >
        <div className="space-y-4">
          {assignMutation.isError && (
            <div className="rounded-md bg-red-50 p-3">
              <p className="text-sm text-red-800">Failed to assign role. Please try again.</p>
            </div>
          )}

          <div>
            <label htmlFor="assign-user" className="block text-sm font-medium text-gray-700 mb-1">
              User
            </label>
            <select
              id="assign-user"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              value={selectedUserId}
              onChange={(e) => setSelectedUserId(Number(e.target.value))}
            >
              <option value={0}>Select a user...</option>
              {users?.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name} ({u.email})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="assign-role" className="block text-sm font-medium text-gray-700 mb-1">
              Role
            </label>
            <select
              id="assign-role"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              value={selectedRoleId}
              onChange={(e) => setSelectedRoleId(Number(e.target.value))}
            >
              <option value={0}>Select a role...</option>
              {roles?.map((r) => (
                <option key={r.id} value={r.id}>
                  {ROLE_LABELS[r.name] ?? r.name}
                </option>
              ))}
            </select>
          </div>

          <ModalFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setAssignModalOpen(false)}
              disabled={assignMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={handleAssign}
              isLoading={assignMutation.isPending}
              disabled={!selectedUserId || !selectedRoleId}
            >
              Assign Role
            </Button>
          </ModalFooter>
        </div>
      </Modal>
    </Card>
  );
}

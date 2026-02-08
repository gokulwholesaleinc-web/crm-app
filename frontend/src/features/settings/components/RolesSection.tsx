/**
 * Roles management section for Settings page.
 * Only visible to admins; lists all roles and their permissions.
 */

import { useState, useEffect } from 'react';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Spinner } from '../../../components/ui/Spinner';
import { Badge } from '../../../components/ui/Badge';
import { usePermissions } from '../../../hooks/usePermissions';
import { rolesApi } from '../../../api/roles';
import type { Role } from '../../../types';
import {
  ShieldCheckIcon,
  CheckIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

const ROLE_COLORS: Record<string, 'purple' | 'blue' | 'green' | 'gray'> = {
  admin: 'purple',
  manager: 'blue',
  sales_rep: 'green',
  viewer: 'gray',
};

const ENTITY_LABELS: Record<string, string> = {
  leads: 'Leads',
  contacts: 'Contacts',
  companies: 'Companies',
  opportunities: 'Opportunities',
  activities: 'Activities',
  campaigns: 'Campaigns',
  workflows: 'Workflows',
  reports: 'Reports',
  settings: 'Settings',
  users: 'Users',
  roles: 'Roles',
};

const ACTIONS = ['create', 'read', 'update', 'delete'];

export function RolesSection() {
  const { isAdmin } = usePermissions();
  const [roles, setRoles] = useState<Role[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAdmin) return;

    let cancelled = false;
    const fetchRoles = async () => {
      try {
        const data = await rolesApi.listRoles();
        if (!cancelled) {
          setRoles(data);
          setError(null);
        }
      } catch {
        if (!cancelled) {
          setError('Failed to load roles');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    fetchRoles();
    return () => { cancelled = true; };
  }, [isAdmin]);

  if (!isAdmin) return null;

  return (
    <Card>
      <CardHeader
        title="Roles & Permissions"
        description="View role-based access control configuration"
      />
      <CardBody className="p-4 sm:p-6">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Spinner size="md" />
          </div>
        ) : error ? (
          <p className="text-sm text-red-600 text-center py-4">{error}</p>
        ) : roles.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-4">
            No roles configured.
          </p>
        ) : (
          <div className="space-y-6">
            {/* Role Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {roles.map((role) => (
                <div
                  key={role.id}
                  className="bg-gray-50 rounded-lg p-4 border border-gray-200"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <ShieldCheckIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
                    <Badge
                      variant={ROLE_COLORS[role.name] || 'gray'}
                      size="md"
                    >
                      {role.name.replace('_', ' ')}
                    </Badge>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {role.description || 'No description'}
                  </p>
                </div>
              ))}
            </div>

            {/* Permissions Matrix */}
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left py-2 pr-4 font-medium text-gray-700">
                      Entity
                    </th>
                    {roles.map((role) => (
                      <th
                        key={role.id}
                        className="text-center px-2 py-2 font-medium text-gray-700 capitalize"
                      >
                        {role.name.replace('_', ' ')}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {Object.entries(ENTITY_LABELS).map(([entity, label]) => (
                    <tr key={entity} className="hover:bg-gray-50">
                      <td className="py-2 pr-4 font-medium text-gray-600">
                        {label}
                      </td>
                      {roles.map((role) => {
                        const perms = role.permissions?.[entity] || [];
                        const hasAll = ACTIONS.every((a) => perms.includes(a));
                        const hasNone = perms.length === 0;
                        const readOnly =
                          perms.length === 1 && perms[0] === 'read';

                        return (
                          <td
                            key={role.id}
                            className="text-center px-2 py-2"
                          >
                            {hasAll ? (
                              <span className="inline-flex items-center text-green-600">
                                <CheckIcon className="h-4 w-4" aria-hidden="true" />
                                <span className="sr-only">Full access</span>
                                <span className="ml-1 text-xs">Full</span>
                              </span>
                            ) : hasNone ? (
                              <span className="inline-flex items-center text-gray-400">
                                <XMarkIcon className="h-4 w-4" aria-hidden="true" />
                                <span className="sr-only">No access</span>
                                <span className="ml-1 text-xs">None</span>
                              </span>
                            ) : readOnly ? (
                              <span className="text-xs text-blue-600">Read</span>
                            ) : (
                              <span className="text-xs text-yellow-600">
                                {perms.join(', ')}
                              </span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

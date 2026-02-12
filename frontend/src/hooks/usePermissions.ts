/**
 * Hook for checking user permissions based on RBAC role.
 *
 * Uses the user's role from the auth store to determine permissions client-side.
 * Server-side enforcement is the source of truth; this is for UI purposes.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../store/authStore';
import type { RoleName } from '../store/authStore';
import { rolesApi } from '../api/roles';
import { CACHE_TIMES } from '../config/queryConfig';
import type { UserRoleAssign } from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const roleKeys = {
  all: ['roles'] as const,
  list: () => [...roleKeys.all, 'list'] as const,
  myPermissions: () => [...roleKeys.all, 'my-permissions'] as const,
};

// =============================================================================
// Server-side Roles & Permissions Hooks
// =============================================================================

/**
 * Hook to fetch all available roles from the server
 */
export function useRoles() {
  return useQuery({
    queryKey: roleKeys.list(),
    queryFn: () => rolesApi.listRoles(),
    ...CACHE_TIMES.REFERENCE,
  });
}

/**
 * Hook to fetch the current user's permissions from the server
 */
export function useMyPermissions() {
  return useQuery({
    queryKey: roleKeys.myPermissions(),
    queryFn: () => rolesApi.getMyPermissions(),
    ...CACHE_TIMES.REFERENCE,
  });
}

/**
 * Hook to assign a role to a user (admin-only)
 */
export function useAssignRole() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UserRoleAssign) => rolesApi.assignRole(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: roleKeys.all });
    },
  });
}

const DEFAULT_PERMISSIONS: Record<RoleName, Record<string, string[]>> = {
  admin: {
    leads: ['create', 'read', 'update', 'delete'],
    contacts: ['create', 'read', 'update', 'delete'],
    companies: ['create', 'read', 'update', 'delete'],
    opportunities: ['create', 'read', 'update', 'delete'],
    activities: ['create', 'read', 'update', 'delete'],
    campaigns: ['create', 'read', 'update', 'delete'],
    workflows: ['create', 'read', 'update', 'delete'],
    reports: ['create', 'read', 'update', 'delete'],
    settings: ['create', 'read', 'update', 'delete'],
    users: ['create', 'read', 'update', 'delete'],
    roles: ['create', 'read', 'update', 'delete'],
  },
  manager: {
    leads: ['create', 'read', 'update', 'delete'],
    contacts: ['create', 'read', 'update', 'delete'],
    companies: ['create', 'read', 'update', 'delete'],
    opportunities: ['create', 'read', 'update', 'delete'],
    activities: ['create', 'read', 'update', 'delete'],
    campaigns: ['create', 'read', 'update', 'delete'],
    workflows: ['create', 'read', 'update', 'delete'],
    reports: ['read'],
    settings: ['read'],
    users: ['read'],
    roles: ['read'],
  },
  sales_rep: {
    leads: ['create', 'read', 'update', 'delete'],
    contacts: ['create', 'read', 'update', 'delete'],
    companies: ['create', 'read', 'update', 'delete'],
    opportunities: ['create', 'read', 'update', 'delete'],
    activities: ['create', 'read', 'update', 'delete'],
    campaigns: ['read'],
    workflows: ['read'],
    reports: ['read'],
    settings: ['read'],
    users: ['read'],
    roles: [],
  },
  viewer: {
    leads: ['read'],
    contacts: ['read'],
    companies: ['read'],
    opportunities: ['read'],
    activities: ['read'],
    campaigns: ['read'],
    workflows: ['read'],
    reports: ['read'],
    settings: ['read'],
    users: ['read'],
    roles: [],
  },
};

export function usePermissions() {
  const user = useAuthStore((state) => state.user);

  const role: RoleName = (user?.role as RoleName) || 'sales_rep';
  const isAdmin = role === 'admin' || user?.is_superuser === true;
  const isManager = role === 'manager';
  const isManagerOrAbove = isAdmin || isManager;

  const permissions = DEFAULT_PERMISSIONS[role] || DEFAULT_PERMISSIONS.sales_rep;

  function hasPermission(entity: string, action: string): boolean {
    if (user?.is_superuser) return true;
    const entityPerms = permissions[entity];
    if (!entityPerms) return false;
    return entityPerms.includes(action);
  }

  function canCreate(entity: string): boolean {
    return hasPermission(entity, 'create');
  }

  function canRead(entity: string): boolean {
    return hasPermission(entity, 'read');
  }

  function canUpdate(entity: string): boolean {
    return hasPermission(entity, 'update');
  }

  function canDelete(entity: string): boolean {
    return hasPermission(entity, 'delete');
  }

  return {
    role,
    isAdmin,
    isManager,
    isManagerOrAbove,
    permissions,
    hasPermission,
    canCreate,
    canRead,
    canUpdate,
    canDelete,
  };
}

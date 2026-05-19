/**
 * Hook for checking the current user's effective RBAC permissions.
 *
 * Server-side permissions are the source of truth for UI gates. The role-based
 * matrix below is only a loading/offline fallback.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../store/authStore';
import type { RoleName } from '../store/authStore';
import { rolesApi } from '../api/roles';
import { CACHE_TIMES } from '../config/queryConfig';
import type { Role, UserPermissions, UserRoleAssign } from '../types';

// Query Keys

export const roleKeys = {
  all: ['roles'] as const,
  list: () => [...roleKeys.all, 'list'] as const,
  myPermissions: (userId?: number) =>
    [...roleKeys.all, 'my-permissions', userId ?? 'anonymous'] as const,
};

type PermissionMap = Record<string, string[]>;

const RETIRED_PERMISSION_ENTITIES = new Set(['opportunities']);

function omitRetiredPermissions(permissions: PermissionMap): PermissionMap {
  return Object.fromEntries(
    Object.entries(permissions).filter(([entity]) => !RETIRED_PERMISSION_ENTITIES.has(entity))
  );
}

// Server-side Roles & Permissions Hooks

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
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const authLoading = useAuthStore((state) => state.isLoading);

  return useQuery({
    queryKey: roleKeys.myPermissions(user?.id),
    queryFn: () => rolesApi.getMyPermissions(),
    enabled: isAuthenticated && !authLoading && !!user,
    select: (data: UserPermissions): UserPermissions => ({
      ...data,
      permissions: omitRetiredPermissions(data.permissions),
    }),
    ...CACHE_TIMES.REFERENCE,
  });
}

/**
 * Hook to assign a role to a user (admin-only)
 */
export function useAssignRole() {
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((state) => state.user);
  const updateUser = useAuthStore((state) => state.updateUser);

  return useMutation({
    mutationFn: (data: UserRoleAssign) => rolesApi.assignRole(data),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: roleKeys.all });
      queryClient.invalidateQueries({ queryKey: ['auth'] });

      if (currentUser?.id === variables.user_id) {
        const roles = queryClient.getQueryData<Role[]>(roleKeys.list());
        const assignedRole = roles?.find((role) => role.id === variables.role_id);
        if (assignedRole?.name) {
          updateUser({ role: assignedRole.name });
        }
      }
    },
  });
}

const DEFAULT_PERMISSIONS: Record<RoleName, PermissionMap> = {
  admin: {
    leads: ['create', 'read', 'update', 'delete'],
    contacts: ['create', 'read', 'update', 'delete'],
    companies: ['create', 'read', 'update', 'delete'],
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
  const permissionsQuery = useMyPermissions();

  const fallbackRole: RoleName = (user?.role as RoleName) || 'sales_rep';
  const fallbackPermissions = DEFAULT_PERMISSIONS[fallbackRole];
  const serverPermissions = permissionsQuery.data?.permissions;
  const permissions = serverPermissions || fallbackPermissions;
  const role = permissionsQuery.data?.role || fallbackRole;
  const isUsingFallbackPermissions = !serverPermissions;

  const isAdmin = role === 'admin' || user?.is_superuser === true;
  const isManager = role === 'manager';
  const isManagerOrAbove = isAdmin || isManager;

  // Deny-by-default while the permissions endpoint is loading OR errored.
  // Without this, the auth-store's `user.role` immediately grants the full
  // DEFAULT_PERMISSIONS map client-side — meaning an admin-flagged user
  // who lost their permission row (or hits a 500 / network blip while
  // /api/roles/me/permissions is in flight) gets full CRUD UI for a few
  // hundred ms. Superusers bypass since their flag IS the source of
  // truth and is set at auth time, not via the permissions query.
  const serverGateUnresolved =
    !user?.is_superuser &&
    (permissionsQuery.isLoading || permissionsQuery.isError) &&
    !serverPermissions;

  function hasPermission(entity: string, action: string): boolean {
    if (user?.is_superuser) return true;
    if (serverGateUnresolved) return false;
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
    isLoading: permissionsQuery.isLoading,
    isError: permissionsQuery.isError,
    isUsingFallbackPermissions,
  };
}

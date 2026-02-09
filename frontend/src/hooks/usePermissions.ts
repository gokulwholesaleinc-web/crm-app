/**
 * React Query hooks for the Roles & Permissions API.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthEnabled } from './useAuthQuery';
import { rolesApi } from '../api/roles';
import type { UserRoleAssign } from '../api/roles';

export const roleKeys = {
  all: ['roles'] as const,
  lists: () => ['roles', 'list'] as const,
  detail: (id: number) => ['roles', 'detail', id] as const,
  userRole: (userId: number) => ['roles', 'user', userId] as const,
  myPermissions: () => ['roles', 'me', 'permissions'] as const,
};

export function useRoles() {
  const authEnabled = useAuthEnabled();
  return useQuery({
    queryKey: roleKeys.lists(),
    queryFn: rolesApi.list,
    enabled: authEnabled,
  });
}

export function useRole(id: number) {
  const authEnabled = useAuthEnabled();
  return useQuery({
    queryKey: roleKeys.detail(id),
    queryFn: () => rolesApi.getById(id),
    enabled: authEnabled && id > 0,
  });
}

export function useMyPermissions() {
  const authEnabled = useAuthEnabled();
  return useQuery({
    queryKey: roleKeys.myPermissions(),
    queryFn: rolesApi.getMyPermissions,
    enabled: authEnabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useUserRole(userId: number) {
  const authEnabled = useAuthEnabled();
  return useQuery({
    queryKey: roleKeys.userRole(userId),
    queryFn: () => rolesApi.getUserRole(userId),
    enabled: authEnabled && userId > 0,
  });
}

export function useCreateRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; description?: string; permissions?: Record<string, string[]> }) =>
      rolesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: roleKeys.lists() });
    },
  });
}

export function useUpdateRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: { name?: string; description?: string; permissions?: Record<string, string[]> } }) =>
      rolesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: roleKeys.all });
    },
  });
}

export function useDeleteRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => rolesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: roleKeys.lists() });
    },
  });
}

export function useAssignRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: UserRoleAssign) => rolesApi.assign(data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: roleKeys.userRole(variables.user_id) });
      queryClient.invalidateQueries({ queryKey: roleKeys.myPermissions() });
    },
  });
}

/**
 * Hook to check if the current user has a specific permission.
 * Returns a function that checks permission synchronously from cached data.
 */
export function useHasPermission() {
  const { data: permissions } = useMyPermissions();

  return (entityType: string, action: string): boolean => {
    if (!permissions) return false;
    const entityPerms = permissions.permissions[entityType];
    if (!entityPerms) return false;
    return entityPerms.includes(action);
  };
}

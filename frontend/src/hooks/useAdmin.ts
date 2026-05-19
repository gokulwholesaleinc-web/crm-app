/**
 * Admin dashboard hooks using TanStack Query
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminApi } from '../api/admin';
import { useAuthStore } from '../store/authStore';
import { CACHE_TIMES } from '../config/queryConfig';
import type { AdminUserUpdate, AssignRoleRequest } from '../types';
import { authKeys } from './useAuth';
import { roleKeys } from './usePermissions';

export const adminKeys = {
  all: ['admin'] as const,
  users: () => [...adminKeys.all, 'users'] as const,
  stats: () => [...adminKeys.all, 'stats'] as const,
  teamOverview: () => [...adminKeys.all, 'team-overview'] as const,
  activityFeed: (limit?: number) => [...adminKeys.all, 'activity-feed', { limit }] as const,
};

export function useAdminUsers() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const authLoading = useAuthStore((s) => s.isLoading);
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.is_superuser === true || user?.role === 'admin';
  return useQuery({
    queryKey: adminKeys.users(),
    queryFn: () => adminApi.getAdminUsers(),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading && isAdmin,
  });
}

export function useSystemStats() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const authLoading = useAuthStore((s) => s.isLoading);
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.is_superuser === true || user?.role === 'admin';
  return useQuery({
    queryKey: adminKeys.stats(),
    queryFn: () => adminApi.getSystemStats(),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading && isAdmin,
  });
}

export function useTeamOverview() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const authLoading = useAuthStore((s) => s.isLoading);
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.is_superuser === true || user?.role === 'admin';
  return useQuery({
    queryKey: adminKeys.teamOverview(),
    queryFn: () => adminApi.getTeamOverview(),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading && isAdmin,
  });
}

export function useActivityFeed(limit = 50) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const authLoading = useAuthStore((s) => s.isLoading);
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.is_superuser === true || user?.role === 'admin';
  return useQuery({
    queryKey: adminKeys.activityFeed(limit),
    queryFn: () => adminApi.getActivityFeed(limit),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading && isAdmin,
  });
}

export function useUpdateAdminUser() {
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((s) => s.user);
  const updateUser = useAuthStore((s) => s.updateUser);

  return useMutation({
    mutationFn: ({ userId, data }: { userId: number; data: AdminUserUpdate }) =>
      adminApi.updateAdminUser(userId, data),
    onSuccess: (updatedUser, variables) => {
      queryClient.invalidateQueries({ queryKey: adminKeys.users() });
      queryClient.invalidateQueries({ queryKey: adminKeys.teamOverview() });
      if (variables.data.role) {
        queryClient.invalidateQueries({ queryKey: roleKeys.all });
        queryClient.invalidateQueries({ queryKey: authKeys.all });
      }
      if (currentUser?.id === variables.userId) {
        updateUser({
          email: updatedUser.email,
          full_name: updatedUser.full_name,
          is_active: updatedUser.is_active,
          is_superuser: updatedUser.is_superuser,
          role: updatedUser.role,
        });
      }
    },
  });
}

export function useDeactivateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: number) => adminApi.deactivateUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.users() });
      queryClient.invalidateQueries({ queryKey: adminKeys.stats() });
      queryClient.invalidateQueries({ queryKey: adminKeys.teamOverview() });
    },
  });
}

export function useAssignUserRole() {
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((s) => s.user);
  const updateUser = useAuthStore((s) => s.updateUser);

  return useMutation({
    mutationFn: ({ userId, data }: { userId: number; data: AssignRoleRequest }) =>
      adminApi.assignUserRole(userId, data),
    onSuccess: (updatedUser, variables) => {
      queryClient.invalidateQueries({ queryKey: adminKeys.users() });
      queryClient.invalidateQueries({ queryKey: adminKeys.teamOverview() });
      queryClient.invalidateQueries({ queryKey: roleKeys.all });
      queryClient.invalidateQueries({ queryKey: authKeys.all });
      if (currentUser?.id === variables.userId) {
        updateUser({
          is_superuser: updatedUser.is_superuser,
          role: updatedUser.role,
        });
      }
    },
  });
}

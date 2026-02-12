/**
 * Admin dashboard hooks using TanStack Query
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminApi } from '../api/admin';
import { useAuthStore } from '../store/authStore';
import { CACHE_TIMES } from '../config/queryConfig';
import type { AdminUserUpdate, AssignRoleRequest } from '../types';

export const adminKeys = {
  all: ['admin'] as const,
  users: () => [...adminKeys.all, 'users'] as const,
  stats: () => [...adminKeys.all, 'stats'] as const,
  teamOverview: () => [...adminKeys.all, 'team-overview'] as const,
  activityFeed: (limit?: number) => [...adminKeys.all, 'activity-feed', { limit }] as const,
  cacheStats: () => [...adminKeys.all, 'cache-stats'] as const,
};

export function useAdminUsers() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: adminKeys.users(),
    queryFn: () => adminApi.getAdminUsers(),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

export function useSystemStats() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: adminKeys.stats(),
    queryFn: () => adminApi.getSystemStats(),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

export function useTeamOverview() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: adminKeys.teamOverview(),
    queryFn: () => adminApi.getTeamOverview(),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

export function useActivityFeed(limit = 50) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: adminKeys.activityFeed(limit),
    queryFn: () => adminApi.getActivityFeed(limit),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

export function useUpdateAdminUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, data }: { userId: number; data: AdminUserUpdate }) =>
      adminApi.updateAdminUser(userId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.users() });
      queryClient.invalidateQueries({ queryKey: adminKeys.teamOverview() });
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
  return useMutation({
    mutationFn: ({ userId, data }: { userId: number; data: AssignRoleRequest }) =>
      adminApi.assignUserRole(userId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.users() });
      queryClient.invalidateQueries({ queryKey: adminKeys.teamOverview() });
    },
  });
}

export function useCacheStats() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: adminKeys.cacheStats(),
    queryFn: () => adminApi.getCacheStats(),
    staleTime: 10 * 1000,
    refetchInterval: 30 * 1000,
    enabled: isAuthenticated && !authLoading,
  });
}

export function useClearAllCache() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => adminApi.clearAllCache(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.cacheStats() });
    },
  });
}

export function useClearCachePattern() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (pattern: string) => adminApi.clearCachePattern(pattern),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminKeys.cacheStats() });
    },
  });
}

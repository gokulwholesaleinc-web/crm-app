/**
 * React Query hooks for notifications with 30-second polling.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { notificationsApi } from '../api/notifications';
import { CACHE_TIMES } from '../config/queryConfig';

export const notificationKeys = {
  all: ['notifications'] as const,
  list: (params?: Record<string, unknown>) => [...notificationKeys.all, 'list', params] as const,
  unreadCount: ['notifications', 'unread-count'] as const,
};

export function useNotifications(params?: {
  page?: number;
  page_size?: number;
  unread_only?: boolean;
}) {
  return useQuery({
    queryKey: notificationKeys.list(params as Record<string, unknown>),
    queryFn: () => notificationsApi.list(params),
    ...CACHE_TIMES.REALTIME,
  });
}

export function useUnreadCount() {
  return useQuery({
    queryKey: notificationKeys.unreadCount,
    queryFn: () => notificationsApi.getUnreadCount(),
    ...CACHE_TIMES.REALTIME,
    refetchInterval: 60000,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => notificationsApi.markRead(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.all });
      queryClient.invalidateQueries({ queryKey: notificationKeys.unreadCount });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => notificationsApi.markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.all });
      queryClient.invalidateQueries({ queryKey: notificationKeys.unreadCount });
    },
  });
}

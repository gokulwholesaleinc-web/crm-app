/**
 * Notifications API client
 */

import { apiClient } from './client';

export interface NotificationItem {
  id: number;
  user_id: number;
  type: string;
  title: string;
  message: string;
  entity_type: string | null;
  entity_id: number | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface UnreadCountResponse {
  count: number;
}

export const notificationsApi = {
  list: (params?: { page?: number; page_size?: number; unread_only?: boolean }) =>
    apiClient.get<NotificationListResponse>('/api/notifications', { params }).then((r) => r.data),

  getUnreadCount: () =>
    apiClient.get<UnreadCountResponse>('/api/notifications/unread-count').then((r) => r.data),

  markRead: (id: number) =>
    apiClient.put<NotificationItem>(`/api/notifications/${id}/read`).then((r) => r.data),

  markAllRead: () =>
    apiClient.put<{ updated: number }>('/api/notifications/read-all').then((r) => r.data),
};

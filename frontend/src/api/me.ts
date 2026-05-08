/**
 * API helpers for the current-user (/api/me/*) namespace.
 */

import { apiClient } from './client';

export interface SharedWithMeItem {
  entity_type: string;
  entity_id: number;
  title: string;
  owner_name: string | null;
  shared_at: string; // ISO-8601 datetime
  permission_level: 'view' | 'edit' | 'assignee';
}

export interface SharedWithMeResponse {
  items_by_type: Record<string, SharedWithMeItem[]>;
  total: number;
}

export async function fetchSharedWithMe(): Promise<SharedWithMeResponse> {
  const response = await apiClient.get<SharedWithMeResponse>('/api/me/shared');
  return response.data;
}

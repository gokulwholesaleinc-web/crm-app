/**
 * Sharing API - share entities with other users
 */

import { apiClient } from './client';

export type PermissionLevel = 'view' | 'edit' | 'assignee';

export interface ShareRequest {
  entity_type: string;
  entity_id: number;
  shared_with_user_id: number;
  permission_level?: PermissionLevel;
}

export interface ShareResponse {
  id: number;
  entity_type: string;
  entity_id: number;
  shared_with_user_id: number;
  shared_by_user_id: number;
  permission_level: string;
}

export interface ShareListResponse {
  items: ShareResponse[];
}

const BASE = '/api/sharing';

export const shareEntity = async (data: ShareRequest): Promise<ShareResponse> => {
  const response = await apiClient.post<ShareResponse>(BASE, data);
  return response.data;
};

export const listEntityShares = async (
  entityType: string,
  entityId: number,
): Promise<ShareListResponse> => {
  const response = await apiClient.get<ShareListResponse>(
    `${BASE}/${entityType}/${entityId}`,
  );
  return response.data;
};

export const revokeShare = async (shareId: number): Promise<void> => {
  await apiClient.delete(`${BASE}/${shareId}`);
};

export const sharingApi = {
  share: shareEntity,
  list: listEntityShares,
  revoke: revokeShare,
};

// ---------------------------------------------------------------------------
// Admin listing types and functions
// ---------------------------------------------------------------------------

export interface AdminShareItem {
  id: number;
  entity_type: string;
  entity_id: number;
  shared_with_user_id: number;
  shared_with_user_name: string;
  shared_with_user_email: string;
  shared_by_user_id: number;
  shared_by_user_name: string;
  permission_level: string;
  created_at: string;
}

export interface AdminShareListResponse {
  items: AdminShareItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminShareFilters {
  entity_type?: string;
  shared_with_user_id?: number;
  shared_by_user_id?: number;
  permission_level?: string;
  page?: number;
  page_size?: number;
}

export const listAdminShares = async (
  filters: AdminShareFilters = {},
): Promise<AdminShareListResponse> => {
  const params: Record<string, string | number> = {};
  if (filters.entity_type) params.entity_type = filters.entity_type;
  if (filters.shared_with_user_id != null) params.shared_with_user_id = filters.shared_with_user_id;
  if (filters.shared_by_user_id != null) params.shared_by_user_id = filters.shared_by_user_id;
  if (filters.permission_level) params.permission_level = filters.permission_level;
  if (filters.page != null) params.page = filters.page;
  if (filters.page_size != null) params.page_size = filters.page_size;
  const response = await apiClient.get<AdminShareListResponse>(`${BASE}/admin`, { params });
  return response.data;
};


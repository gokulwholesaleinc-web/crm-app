/**
 * Sharing API - share entities with other users
 */

import { apiClient } from './client';

export interface ShareRequest {
  entity_type: string;
  entity_id: number;
  shared_with_user_id: number;
  permission_level?: 'view' | 'edit';
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

export default sharingApi;

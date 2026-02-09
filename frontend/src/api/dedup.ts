/**
 * Duplicate Detection API
 */

import { apiClient } from './client';

export interface DuplicateMatch {
  id: number;
  entity_type: string;
  display_name: string;
  email: string | null;
  phone: string | null;
  match_reason: string;
}

export interface DedupCheckResponse {
  duplicates: DuplicateMatch[];
  has_duplicates: boolean;
}

export interface MergeResponse {
  success: boolean;
  primary_id: number;
  message: string;
}

const BASE = '/api/dedup';

export const checkDuplicates = async (
  entityType: string,
  data: Record<string, unknown>,
): Promise<DedupCheckResponse> => {
  const response = await apiClient.post<DedupCheckResponse>(`${BASE}/check`, {
    entity_type: entityType,
    data,
  });
  return response.data;
};

export const mergeEntities = async (
  entityType: string,
  primaryId: number,
  secondaryId: number,
): Promise<MergeResponse> => {
  const response = await apiClient.post<MergeResponse>(`${BASE}/merge`, {
    entity_type: entityType,
    primary_id: primaryId,
    secondary_id: secondaryId,
  });
  return response.data;
};

export const dedupApi = {
  check: checkDuplicates,
  merge: mergeEntities,
};

export default dedupApi;

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

export type DedupEntityType = 'contacts' | 'companies' | 'leads';
export type DedupClusterKey = 'email' | 'phone' | 'name';

export interface DedupClusterMember {
  id: number;
  label: string;
  email: string | null;
  phone: string | null;
  company_id: number | null;
  owner_id: number | null;
  created_at: string | null;
  last_activity_at: string | null;
  activity_count: number;
}

export interface DedupCluster {
  key: DedupClusterKey;
  key_value: string;
  member_count: number;
  members: DedupClusterMember[];
}

export interface DedupClustersResponse {
  entity_type: DedupEntityType;
  key: DedupClusterKey;
  clusters: DedupCluster[];
  skipped_no_key: number;
}

export type MergeClusterFailureCode =
  | 'self_merge'
  | 'stale_cluster'
  | 'not_found_primary'
  | 'other';

export interface MergeClusterFailure {
  id: number;
  reason: string;
  reason_code: MergeClusterFailureCode;
}

export interface MergeClusterResponse {
  success: boolean;
  winner_id: number;
  merged_ids: number[];
  failures: MergeClusterFailure[];
}

export const listDuplicateClusters = async (
  entityType: DedupEntityType,
  key: DedupClusterKey,
): Promise<DedupClustersResponse> => {
  const response = await apiClient.get<DedupClustersResponse>(`${BASE}/clusters`, {
    params: { entity_type: entityType, key },
  });
  return response.data;
};

export const mergeCluster = async (
  entityType: DedupEntityType,
  winnerId: number,
  loserIds: number[],
): Promise<MergeClusterResponse> => {
  const response = await apiClient.post<MergeClusterResponse>(`${BASE}/merge-cluster`, {
    entity_type: entityType,
    winner_id: winnerId,
    loser_ids: loserIds,
  });
  return response.data;
};

export const dedupApi = {
  check: checkDuplicates,
  merge: mergeEntities,
  listClusters: listDuplicateClusters,
  mergeCluster,
};


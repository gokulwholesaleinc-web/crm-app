/**
 * Audit Log API
 */

import { apiClient } from './client';
import type {
  AdminAuditEntityDetail,
  AdminAuditFeedFilters,
  AdminAuditFeedResponse,
  AdminAuditSummaryResponse,
  AdminAuditUserDetail,
  AuditLogListResponse,
  WorkSession,
  WorkSessionHeartbeatRequest,
} from '../types';

const AUDIT_BASE = '/api/audit';
const ADMIN_AUDIT_BASE = '/api/admin/audit';
const WORK_SESSIONS_BASE = '/api/work-sessions';

/**
 * Get audit history for a specific entity
 */
export const getEntityAuditLog = async (
  entityType: string,
  entityId: number,
  page = 1,
  pageSize = 20
): Promise<AuditLogListResponse> => {
  const response = await apiClient.get<AuditLogListResponse>(
    `${AUDIT_BASE}/${entityType}/${entityId}`,
    { params: { page, page_size: pageSize } }
  );
  return response.data;
};

export const getAdminAuditFeed = async (
  filters: AdminAuditFeedFilters = {}
): Promise<AdminAuditFeedResponse> => {
  const response = await apiClient.get<AdminAuditFeedResponse>(
    `${ADMIN_AUDIT_BASE}/feed`,
    { params: filters }
  );
  return response.data;
};

export const getAdminAuditSummary = async (
  filters: Omit<AdminAuditFeedFilters, 'page' | 'page_size' | 'entity_id'> = {}
): Promise<AdminAuditSummaryResponse> => {
  const response = await apiClient.get<AdminAuditSummaryResponse>(
    `${ADMIN_AUDIT_BASE}/summary`,
    { params: filters }
  );
  return response.data;
};

export const getAdminAuditUserDetail = async (
  userId: number,
  filters: AdminAuditFeedFilters = {}
): Promise<AdminAuditUserDetail> => {
  const response = await apiClient.get<AdminAuditUserDetail>(
    `${ADMIN_AUDIT_BASE}/users/${userId}`,
    { params: filters }
  );
  return response.data;
};

export const getAdminAuditEntityDetail = async (
  entityType: string,
  entityId: number,
  filters: Omit<AdminAuditFeedFilters, 'entity_type' | 'entity_id'> = {}
): Promise<AdminAuditEntityDetail> => {
  const response = await apiClient.get<AdminAuditEntityDetail>(
    `${ADMIN_AUDIT_BASE}/entities/${entityType}/${entityId}`,
    { params: filters }
  );
  return response.data;
};

export const sendWorkSessionHeartbeat = async (
  payload: WorkSessionHeartbeatRequest
): Promise<WorkSession> => {
  const response = await apiClient.post<WorkSession>(
    `${WORK_SESSIONS_BASE}/heartbeat`,
    payload
  );
  return response.data;
};

export const auditApi = {
  getEntityAuditLog,
  getAdminAuditFeed,
  getAdminAuditSummary,
  getAdminAuditUserDetail,
  getAdminAuditEntityDetail,
  sendWorkSessionHeartbeat,
};

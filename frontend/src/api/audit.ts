/**
 * Audit Log API
 */

import { apiClient } from './client';
import type { AuditLogListResponse } from '../types';

const AUDIT_BASE = '/api/audit';

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

export const auditApi = {
  getEntityAuditLog,
};

export default auditApi;

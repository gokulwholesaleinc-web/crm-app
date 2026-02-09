/**
 * Audit log API client.
 */

import { apiClient } from './client';
import type { AuditLogListResponse } from '../types';

export const auditApi = {
  getEntityLog: (
    entityType: string,
    entityId: number,
    params?: { page?: number; page_size?: number }
  ) =>
    apiClient
      .get<AuditLogListResponse>(`/api/audit/${entityType}/${entityId}`, {
        params,
      })
      .then((r) => r.data),
};

export const getEntityAuditLog = auditApi.getEntityLog;

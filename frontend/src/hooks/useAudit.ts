/**
 * Hooks for audit log (change history).
 */

import { useAuthQuery } from './useAuthQuery';
import { auditApi } from '../api/audit';

export const auditKeys = {
  all: ['audit'] as const,
  entity: (entityType: string, entityId: number) =>
    [...auditKeys.all, entityType, entityId] as const,
  entityPage: (entityType: string, entityId: number, page: number) =>
    [...auditKeys.entity(entityType, entityId), page] as const,
};

export function useEntityAuditLog(
  entityType: string,
  entityId: number,
  page = 1,
  pageSize = 10
) {
  return useAuthQuery({
    queryKey: auditKeys.entityPage(entityType, entityId, page),
    queryFn: () =>
      auditApi.getEntityLog(entityType, entityId, {
        page,
        page_size: pageSize,
      }),
    enabled: !!entityType && !!entityId,
  });
}

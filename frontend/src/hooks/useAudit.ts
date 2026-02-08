/**
 * Audit log hooks using TanStack Query for data fetching and caching.
 */

import { useAuthQuery } from './useAuthQuery';
import { auditApi } from '../api/audit';

// =============================================================================
// Query Keys
// =============================================================================

export const auditKeys = {
  all: ['audit'] as const,
  entity: (entityType: string, entityId: number) =>
    [...auditKeys.all, 'entity', entityType, entityId] as const,
  entityPage: (entityType: string, entityId: number, page: number) =>
    [...auditKeys.entity(entityType, entityId), page] as const,
};

// =============================================================================
// Hooks
// =============================================================================

/**
 * Hook to fetch audit history for a specific entity
 */
export function useEntityAuditLog(
  entityType: string,
  entityId: number,
  page = 1,
  pageSize = 20
) {
  return useAuthQuery({
    queryKey: auditKeys.entityPage(entityType, entityId, page),
    queryFn: () => auditApi.getEntityAuditLog(entityType, entityId, page, pageSize),
    enabled: !!entityType && !!entityId,
  });
}

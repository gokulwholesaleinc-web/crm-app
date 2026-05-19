/**
 * Audit log hooks using TanStack Query for data fetching and caching.
 */

import { useAuthQuery } from './useAuthQuery';
import { auditApi } from '../api/audit';
import { CACHE_TIMES } from '../config/queryConfig';
import { useAuthStore } from '../store/authStore';
import type { AdminAuditFeedFilters } from '../types';

// Query Keys

export const auditKeys = {
  all: ['audit'] as const,
  entity: (entityType: string, entityId: number) =>
    [...auditKeys.all, 'entity', entityType, entityId] as const,
  entityPage: (entityType: string, entityId: number, page: number) =>
    [...auditKeys.entity(entityType, entityId), page] as const,
  admin: () => [...auditKeys.all, 'admin'] as const,
  adminFeed: (filters: AdminAuditFeedFilters) =>
    [...auditKeys.admin(), 'feed', filters] as const,
  adminSummary: (filters: Omit<AdminAuditFeedFilters, 'page' | 'page_size' | 'entity_id'>) =>
    [...auditKeys.admin(), 'summary', filters] as const,
  adminUser: (userId: number, filters: AdminAuditFeedFilters) =>
    [...auditKeys.admin(), 'user', userId, filters] as const,
  adminEntity: (
    entityType: string,
    entityId: number,
    filters: Omit<AdminAuditFeedFilters, 'entity_type' | 'entity_id'>,
  ) => [...auditKeys.admin(), 'entity', entityType, entityId, filters] as const,
};

// Hooks

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

function useIsAdmin(): boolean {
  const user = useAuthStore((s) => s.user);
  return user?.is_superuser === true || user?.role === 'admin';
}

export function useAdminAuditFeed(filters: AdminAuditFeedFilters) {
  const isAdmin = useIsAdmin();
  return useAuthQuery({
    queryKey: auditKeys.adminFeed(filters),
    queryFn: () => auditApi.getAdminAuditFeed(filters),
    ...CACHE_TIMES.REALTIME,
    // 2 minutes, not 30s. Audit feed is one of the heavier admin queries
    // (audit_logs joined to users, JSON `changes` cast for search). 30s
    // polling from a single open admin tab was ~2,880 queries/day per
    // admin — Neon compute was the bottleneck, not freshness. The page
    // has an explicit Refresh button for "I need it now" cases.
    refetchInterval: isAdmin ? 120 * 1000 : false,
    enabled: isAdmin,
  });
}

export function useAdminAuditSummary(
  filters: Omit<AdminAuditFeedFilters, 'page' | 'page_size' | 'entity_id'>
) {
  const isAdmin = useIsAdmin();
  return useAuthQuery({
    queryKey: auditKeys.adminSummary(filters),
    queryFn: () => auditApi.getAdminAuditSummary(filters),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAdmin,
  });
}

export function useAdminAuditUserDetail(userId: number, filters: AdminAuditFeedFilters) {
  const isAdmin = useIsAdmin();
  return useAuthQuery({
    queryKey: auditKeys.adminUser(userId, filters),
    queryFn: () => auditApi.getAdminAuditUserDetail(userId, filters),
    ...CACHE_TIMES.DETAIL,
    enabled: isAdmin && Boolean(userId),
  });
}

export function useAdminAuditEntityDetail(
  entityType: string,
  entityId: number,
  filters: Omit<AdminAuditFeedFilters, 'entity_type' | 'entity_id'>
) {
  const isAdmin = useIsAdmin();
  return useAuthQuery({
    queryKey: auditKeys.adminEntity(entityType, entityId, filters),
    queryFn: () => auditApi.getAdminAuditEntityDetail(entityType, entityId, filters),
    ...CACHE_TIMES.DETAIL,
    enabled: isAdmin && Boolean(entityType) && Boolean(entityId),
  });
}

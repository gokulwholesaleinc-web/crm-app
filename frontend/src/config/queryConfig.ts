/**
 * Centralized React Query cache time configuration.
 *
 * staleTime: How long data is considered fresh (won't refetch on mount).
 * gcTime: How long inactive data stays in cache before garbage collection.
 */
export const CACHE_TIMES = {
  /** Reference data - rarely changes (10 min stale, 30 min cache) */
  REFERENCE: { staleTime: 10 * 60 * 1000, gcTime: 30 * 60 * 1000 },

  /** Entity lists - moderate freshness (2 min stale, 10 min cache) */
  LIST: { staleTime: 2 * 60 * 1000, gcTime: 10 * 60 * 1000 },

  /** Entity detail - needs freshness (30 sec stale, 5 min cache) */
  DETAIL: { staleTime: 30 * 1000, gcTime: 5 * 60 * 1000 },

  /** Dashboard - moderate (5 min stale, 10 min cache) */
  DASHBOARD: { staleTime: 5 * 60 * 1000, gcTime: 10 * 60 * 1000 },

  /** Real-time - always fresh (0 stale) */
  REALTIME: { staleTime: 10 * 1000, gcTime: 60 * 1000 },
} as const;

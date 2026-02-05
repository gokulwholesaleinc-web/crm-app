/**
 * Auth-aware query helpers to avoid repeating auth checks in every hook.
 */

import { useQuery, UseQueryOptions, QueryKey } from '@tanstack/react-query';
import { useAuthStore } from '../store/authStore';

/**
 * Returns the enabled condition for auth-dependent queries.
 * Use this in existing hooks that need to wait for authentication.
 */
export function useAuthEnabled(): boolean {
  const { isAuthenticated, isLoading } = useAuthStore();
  return isAuthenticated && !isLoading;
}

/**
 * A wrapper around useQuery that automatically adds auth-based enabled condition.
 * Combines with any existing enabled condition using AND logic.
 */
export function useAuthQuery<
  TQueryFnData = unknown,
  TError = Error,
  TData = TQueryFnData,
  TQueryKey extends QueryKey = QueryKey,
>(
  options: UseQueryOptions<TQueryFnData, TError, TData, TQueryKey>
): ReturnType<typeof useQuery<TQueryFnData, TError, TData, TQueryKey>> {
  const authEnabled = useAuthEnabled();
  const userEnabled = options.enabled ?? true;

  return useQuery({
    ...options,
    enabled: authEnabled && userEnabled,
  });
}

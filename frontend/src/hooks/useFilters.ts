/**
 * Saved Filters hooks using TanStack Query.
 * Provides hooks for listing, creating, and deleting saved filter presets.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { filtersApi } from '../api/filters';
import type { SavedFilterCreate } from '../api/filters';
import { useAuthQuery } from './useAuthQuery';

// =============================================================================
// Query Keys
// =============================================================================

export const filterKeys = {
  all: ['filters'] as const,
  lists: () => ['filters', 'list'] as const,
  list: (entityType?: string) => ['filters', 'list', entityType] as const,
};

// =============================================================================
// Query Hooks
// =============================================================================

export function useSavedFilters(entityType?: string) {
  return useAuthQuery({
    queryKey: filterKeys.list(entityType),
    queryFn: () => filtersApi.listSavedFilters(entityType),
  });
}

// =============================================================================
// Mutation Hooks
// =============================================================================

export function useCreateSavedFilter() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: SavedFilterCreate) => filtersApi.createSavedFilter(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: filterKeys.lists() });
    },
  });
}

export function useDeleteSavedFilter() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => filtersApi.deleteSavedFilter(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: filterKeys.lists() });
    },
  });
}

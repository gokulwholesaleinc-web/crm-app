/**
 * Filter hooks using TanStack Query.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthQuery } from './useAuthQuery';
import {
  listSavedFilters,
  createSavedFilter,
  deleteSavedFilter,
} from '../api/filters';
import type { SavedFilterCreate } from '../api/filters';

export const filterKeys = {
  all: ['filters'] as const,
  byEntity: (entityType: string) => [...filterKeys.all, entityType] as const,
};

export const useSavedFilters = (entityType?: string) =>
  useAuthQuery({
    queryKey: entityType ? filterKeys.byEntity(entityType) : filterKeys.all,
    queryFn: () => listSavedFilters(entityType),
  });

export const useCreateSavedFilter = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SavedFilterCreate) => createSavedFilter(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: filterKeys.all });
    },
  });
};

export const useDeleteSavedFilter = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteSavedFilter(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: filterKeys.all });
    },
  });
};

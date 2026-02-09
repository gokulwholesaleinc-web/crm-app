/**
 * Duplicate detection hooks using TanStack Query.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { dedupApi } from '../api/dedup';

export function useCheckDuplicates() {
  return useMutation({
    mutationFn: ({
      entityType,
      data,
    }: {
      entityType: string;
      data: Record<string, unknown>;
    }) => dedupApi.check(entityType, data),
  });
}

export function useMergeEntities() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      entityType,
      primaryId,
      secondaryId,
    }: {
      entityType: string;
      primaryId: number;
      secondaryId: number;
    }) => dedupApi.merge(entityType, primaryId, secondaryId),
    onSuccess: (_data, variables) => {
      // Invalidate entity lists
      queryClient.invalidateQueries({ queryKey: [variables.entityType] });
    },
  });
}

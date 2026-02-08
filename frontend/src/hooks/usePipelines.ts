/**
 * Pipeline hooks using TanStack Query for data fetching and caching.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthQuery } from './useAuthQuery';
import { pipelinesApi } from '../api/pipelines';
import type { PipelineCreate, PipelineUpdate } from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const pipelineEntityKeys = {
  all: ['pipelines'] as const,
  lists: () => [...pipelineEntityKeys.all, 'list'] as const,
  details: () => [...pipelineEntityKeys.all, 'detail'] as const,
  detail: (id: number) => [...pipelineEntityKeys.details(), id] as const,
};

// =============================================================================
// List and Detail Hooks
// =============================================================================

/**
 * Hook to fetch all pipelines
 */
export function usePipelines() {
  return useAuthQuery({
    queryKey: pipelineEntityKeys.lists(),
    queryFn: () => pipelinesApi.list(),
  });
}

/**
 * Hook to fetch a single pipeline by ID
 */
export function usePipeline(id: number | undefined) {
  return useAuthQuery({
    queryKey: pipelineEntityKeys.detail(id!),
    queryFn: () => pipelinesApi.get(id!),
    enabled: !!id,
  });
}

// =============================================================================
// Mutation Hooks
// =============================================================================

/**
 * Hook to create a new pipeline
 */
export function useCreatePipeline() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: PipelineCreate) => pipelinesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pipelineEntityKeys.lists() });
    },
  });
}

/**
 * Hook to update a pipeline
 */
export function useUpdatePipeline() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: PipelineUpdate }) =>
      pipelinesApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: pipelineEntityKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: pipelineEntityKeys.detail(id),
      });
    },
  });
}

/**
 * Hook to delete a pipeline
 */
export function useDeletePipeline() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => pipelinesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pipelineEntityKeys.lists() });
    },
  });
}

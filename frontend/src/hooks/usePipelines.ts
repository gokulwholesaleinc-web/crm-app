/**
 * Hooks for multiple pipeline management.
 */

import {
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import { useAuthQuery } from './useAuthQuery';
import { pipelinesApi } from '../api/pipelines';
import type { PipelineCreate, PipelineUpdate } from '../types';

export const pipelineEntityKeys = {
  all: ['pipelines'] as const,
  list: () => [...pipelineEntityKeys.all, 'list'] as const,
  detail: (id: number) => [...pipelineEntityKeys.all, 'detail', id] as const,
};

export function usePipelines(page = 1, pageSize = 50) {
  return useAuthQuery({
    queryKey: [...pipelineEntityKeys.list(), page],
    queryFn: () => pipelinesApi.list({ page, page_size: pageSize }),
  });
}

export function usePipeline(id: number) {
  return useAuthQuery({
    queryKey: pipelineEntityKeys.detail(id),
    queryFn: () => pipelinesApi.get(id),
    enabled: !!id,
  });
}

export function useCreatePipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PipelineCreate) => pipelinesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: pipelineEntityKeys.list(),
      });
    },
  });
}

export function useUpdatePipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: PipelineUpdate }) =>
      pipelinesApi.update(id, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: pipelineEntityKeys.list(),
      });
      queryClient.invalidateQueries({
        queryKey: pipelineEntityKeys.detail(variables.id),
      });
    },
  });
}

export function useDeletePipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => pipelinesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: pipelineEntityKeys.list(),
      });
    },
  });
}

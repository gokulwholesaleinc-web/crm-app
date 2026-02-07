/**
 * Workflows hooks using TanStack Query.
 * Provides hooks for listing, creating, updating, and deleting workflow rules.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { workflowsApi } from '../api/workflows';
import { useAuthQuery } from './useAuthQuery';
import type {
  WorkflowRuleCreate,
  WorkflowRuleUpdate,
} from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const workflowKeys = {
  all: ['workflows'] as const,
  lists: () => ['workflows', 'list'] as const,
  list: (params?: { page?: number; page_size?: number; is_active?: boolean; trigger_entity?: string }) =>
    ['workflows', 'list', params] as const,
  details: () => ['workflows', 'detail'] as const,
  detail: (id: number) => ['workflows', 'detail', id] as const,
  executions: (id: number, params?: { page?: number; page_size?: number }) =>
    ['workflows', 'executions', id, params] as const,
};

// =============================================================================
// List & Detail Hooks
// =============================================================================

export function useWorkflows(params?: {
  page?: number;
  page_size?: number;
  is_active?: boolean;
  trigger_entity?: string;
}) {
  return useAuthQuery({
    queryKey: workflowKeys.list(params),
    queryFn: () => workflowsApi.list(params),
  });
}

export function useWorkflow(id: number | undefined) {
  return useAuthQuery({
    queryKey: workflowKeys.detail(id!),
    queryFn: () => workflowsApi.get(id!),
    enabled: !!id,
  });
}

export function useWorkflowExecutions(
  id: number | undefined,
  params?: { page?: number; page_size?: number }
) {
  return useQuery({
    queryKey: workflowKeys.executions(id!, params),
    queryFn: () => workflowsApi.getExecutions(id!, params),
    enabled: !!id,
  });
}

// =============================================================================
// Mutation Hooks
// =============================================================================

export function useCreateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: WorkflowRuleCreate) => workflowsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.lists() });
    },
  });
}

export function useUpdateWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: WorkflowRuleUpdate }) =>
      workflowsApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.lists() });
      queryClient.invalidateQueries({ queryKey: workflowKeys.detail(id) });
    },
  });
}

export function useDeleteWorkflow() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => workflowsApi.delete(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: workflowKeys.lists() });
      queryClient.removeQueries({ queryKey: workflowKeys.detail(id) });
    },
  });
}

export function useTestWorkflow() {
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: { entity_type: string; entity_id: number } }) =>
      workflowsApi.test(id, data),
  });
}

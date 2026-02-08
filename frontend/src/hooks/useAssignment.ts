/**
 * Assignment Rules hooks using TanStack Query.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { assignmentApi } from '../api/assignment';
import { useAuthQuery } from './useAuthQuery';
import type { AssignmentRuleCreate, AssignmentRuleUpdate } from '../types';

export const assignmentKeys = {
  all: ['assignment-rules'] as const,
  lists: () => ['assignment-rules', 'list'] as const,
  details: () => ['assignment-rules', 'detail'] as const,
  detail: (id: number) => ['assignment-rules', 'detail', id] as const,
  stats: (id: number) => ['assignment-rules', 'stats', id] as const,
};

export function useAssignmentRules() {
  return useAuthQuery({
    queryKey: assignmentKeys.lists(),
    queryFn: () => assignmentApi.list(),
  });
}

export function useAssignmentRule(id: number | undefined) {
  return useAuthQuery({
    queryKey: assignmentKeys.detail(id!),
    queryFn: () => assignmentApi.get(id!),
    enabled: !!id,
  });
}

export function useAssignmentStats(id: number | undefined) {
  return useAuthQuery({
    queryKey: assignmentKeys.stats(id!),
    queryFn: () => assignmentApi.getStats(id!),
    enabled: !!id,
  });
}

export function useCreateAssignmentRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: AssignmentRuleCreate) => assignmentApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: assignmentKeys.lists() });
    },
  });
}

export function useUpdateAssignmentRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: AssignmentRuleUpdate }) =>
      assignmentApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: assignmentKeys.lists() });
      queryClient.invalidateQueries({ queryKey: assignmentKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: assignmentKeys.stats(id) });
    },
  });
}

export function useDeleteAssignmentRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => assignmentApi.delete(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: assignmentKeys.lists() });
      queryClient.removeQueries({ queryKey: assignmentKeys.detail(id) });
    },
  });
}

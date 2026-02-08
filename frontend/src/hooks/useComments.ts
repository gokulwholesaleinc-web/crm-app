/**
 * Comment hooks using TanStack Query for data fetching and caching.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthQuery } from './useAuthQuery';
import { commentsApi } from '../api/comments';
import type { CommentCreate, CommentUpdate } from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const commentKeys = {
  all: ['comments'] as const,
  lists: () => [...commentKeys.all, 'list'] as const,
  entity: (entityType: string, entityId: number) =>
    [...commentKeys.all, 'entity', entityType, entityId] as const,
  entityPage: (entityType: string, entityId: number, page: number) =>
    [...commentKeys.entity(entityType, entityId), page] as const,
  details: () => [...commentKeys.all, 'detail'] as const,
  detail: (id: number) => [...commentKeys.details(), id] as const,
};

// =============================================================================
// List and Detail Hooks
// =============================================================================

/**
 * Hook to fetch comments for a specific entity
 */
export function useEntityComments(
  entityType: string,
  entityId: number,
  page = 1,
  pageSize = 50
) {
  return useAuthQuery({
    queryKey: commentKeys.entityPage(entityType, entityId, page),
    queryFn: () =>
      commentsApi.list({
        entity_type: entityType,
        entity_id: entityId,
        page,
        page_size: pageSize,
      }),
    enabled: !!entityType && !!entityId,
  });
}

/**
 * Hook to fetch a single comment by ID
 */
export function useComment(id: number | undefined) {
  return useAuthQuery({
    queryKey: commentKeys.detail(id!),
    queryFn: () => commentsApi.get(id!),
    enabled: !!id,
  });
}

// =============================================================================
// Mutation Hooks
// =============================================================================

/**
 * Hook to create a new comment
 */
export function useCreateComment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CommentCreate) => commentsApi.create(data),
    onSuccess: (newComment) => {
      queryClient.invalidateQueries({ queryKey: commentKeys.lists() });
      queryClient.invalidateQueries({
        queryKey: commentKeys.entity(newComment.entity_type, newComment.entity_id),
      });
    },
  });
}

/**
 * Hook to update a comment
 */
export function useUpdateComment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: CommentUpdate }) =>
      commentsApi.update(id, data),
    onSuccess: (_updatedComment, { id }) => {
      queryClient.invalidateQueries({ queryKey: commentKeys.lists() });
      queryClient.invalidateQueries({ queryKey: commentKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: commentKeys.all });
    },
  });
}

/**
 * Hook to delete a comment
 */
export function useDeleteComment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
    }: {
      id: number;
      entityType: string;
      entityId: number;
    }) => commentsApi.delete(id),
    onSuccess: (_, variables) => {
      const { id, entityType, entityId } = variables;
      queryClient.invalidateQueries({ queryKey: commentKeys.lists() });
      queryClient.invalidateQueries({ queryKey: commentKeys.detail(id) });
      queryClient.invalidateQueries({
        queryKey: commentKeys.entity(entityType, entityId),
      });
    },
  });
}

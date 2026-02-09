/**
 * Hooks for comments (team collaboration).
 */

import {
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import { useAuthQuery } from './useAuthQuery';
import { commentsApi } from '../api/comments';
import type { CommentCreate, CommentUpdate } from '../types';

export const commentKeys = {
  all: ['comments'] as const,
  entity: (entityType: string, entityId: number) =>
    [...commentKeys.all, entityType, entityId] as const,
  entityPage: (entityType: string, entityId: number, page: number) =>
    [...commentKeys.entity(entityType, entityId), page] as const,
};

export function useEntityComments(
  entityType: string,
  entityId: number,
  page = 1,
  pageSize = 20
) {
  return useAuthQuery({
    queryKey: commentKeys.entityPage(entityType, entityId, page),
    queryFn: () =>
      commentsApi.listEntityComments(entityType, entityId, {
        page,
        page_size: pageSize,
      }),
    enabled: !!entityType && !!entityId,
  });
}

export function useCreateComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CommentCreate) => commentsApi.create(data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: commentKeys.entity(variables.entity_type, variables.entity_id),
      });
    },
  });
}

export function useUpdateComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      commentId,
      data,
    }: {
      commentId: number;
      data: CommentUpdate;
      entityType: string;
      entityId: number;
    }) => commentsApi.update(commentId, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: commentKeys.entity(variables.entityType, variables.entityId),
      });
    },
  });
}

export function useDeleteComment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      commentId,
    }: {
      commentId: number;
      entityType: string;
      entityId: number;
    }) => commentsApi.delete(commentId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: commentKeys.entity(variables.entityType, variables.entityId),
      });
    },
  });
}

/**
 * Comments API client.
 */

import { apiClient } from './client';
import type {
  CommentListResponse,
  Comment,
  CommentCreate,
  CommentUpdate,
} from '../types';

export const commentsApi = {
  listEntityComments: (
    entityType: string,
    entityId: number,
    params?: { page?: number; page_size?: number }
  ) =>
    apiClient
      .get<CommentListResponse>(`/api/comments/${entityType}/${entityId}`, {
        params,
      })
      .then((r) => r.data),

  create: (data: CommentCreate) =>
    apiClient.post<Comment>('/api/comments', data).then((r) => r.data),

  update: (commentId: number, data: CommentUpdate) =>
    apiClient
      .patch<Comment>(`/api/comments/${commentId}`, data)
      .then((r) => r.data),

  delete: (commentId: number) =>
    apiClient.delete(`/api/comments/${commentId}`).then((r) => r.data),
};

export const listEntityComments = commentsApi.listEntityComments;
export const createComment = commentsApi.create;
export const updateComment = commentsApi.update;
export const deleteComment = commentsApi.delete;

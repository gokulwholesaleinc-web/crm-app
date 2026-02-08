/**
 * Comments API
 */

import { apiClient } from './client';
import type {
  Comment,
  CommentCreate,
  CommentUpdate,
  CommentListResponse,
  CommentFilters,
} from '../types';

const COMMENTS_BASE = '/api/comments';

/**
 * List comments for an entity
 */
export const listComments = async (
  filters: CommentFilters
): Promise<CommentListResponse> => {
  const response = await apiClient.get<CommentListResponse>(COMMENTS_BASE, {
    params: filters,
  });
  return response.data;
};

/**
 * Get a comment by ID
 */
export const getComment = async (commentId: number): Promise<Comment> => {
  const response = await apiClient.get<Comment>(`${COMMENTS_BASE}/${commentId}`);
  return response.data;
};

/**
 * Create a new comment
 */
export const createComment = async (data: CommentCreate): Promise<Comment> => {
  const response = await apiClient.post<Comment>(COMMENTS_BASE, data);
  return response.data;
};

/**
 * Update a comment
 */
export const updateComment = async (
  commentId: number,
  data: CommentUpdate
): Promise<Comment> => {
  const response = await apiClient.patch<Comment>(
    `${COMMENTS_BASE}/${commentId}`,
    data
  );
  return response.data;
};

/**
 * Delete a comment
 */
export const deleteComment = async (commentId: number): Promise<void> => {
  await apiClient.delete(`${COMMENTS_BASE}/${commentId}`);
};

export const commentsApi = {
  list: listComments,
  get: getComment,
  create: createComment,
  update: updateComment,
  delete: deleteComment,
};

export default commentsApi;

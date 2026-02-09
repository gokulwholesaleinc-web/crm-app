/**
 * Pipelines API client (multiple pipeline management).
 */

import { apiClient } from './client';
import type {
  Pipeline,
  PipelineCreate,
  PipelineUpdate,
  PipelineListResponse,
} from '../types';

export const pipelinesApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    apiClient
      .get<PipelineListResponse>('/api/pipelines', { params })
      .then((r) => r.data),

  get: (id: number) =>
    apiClient.get<Pipeline>(`/api/pipelines/${id}`).then((r) => r.data),

  create: (data: PipelineCreate) =>
    apiClient.post<Pipeline>('/api/pipelines', data).then((r) => r.data),

  update: (id: number, data: PipelineUpdate) =>
    apiClient
      .patch<Pipeline>(`/api/pipelines/${id}`, data)
      .then((r) => r.data),

  delete: (id: number) =>
    apiClient.delete(`/api/pipelines/${id}`).then((r) => r.data),
};

export const listPipelines = pipelinesApi.list;
export const getPipeline = pipelinesApi.get;
export const createPipeline = pipelinesApi.create;
export const updatePipeline = pipelinesApi.update;
export const deletePipeline = pipelinesApi.delete;

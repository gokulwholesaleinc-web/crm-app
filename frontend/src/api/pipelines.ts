/**
 * Pipelines API
 */

import { apiClient } from './client';
import type {
  Pipeline,
  PipelineCreate,
  PipelineUpdate,
  PipelineListResponse,
} from '../types';

const PIPELINES_BASE = '/api/pipelines';

/**
 * List all pipelines
 */
export const listPipelines = async (): Promise<PipelineListResponse> => {
  const response = await apiClient.get<PipelineListResponse>(PIPELINES_BASE);
  return response.data;
};

/**
 * Get a pipeline by ID
 */
export const getPipeline = async (pipelineId: number): Promise<Pipeline> => {
  const response = await apiClient.get<Pipeline>(`${PIPELINES_BASE}/${pipelineId}`);
  return response.data;
};

/**
 * Create a new pipeline
 */
export const createPipeline = async (data: PipelineCreate): Promise<Pipeline> => {
  const response = await apiClient.post<Pipeline>(PIPELINES_BASE, data);
  return response.data;
};

/**
 * Update a pipeline
 */
export const updatePipeline = async (
  pipelineId: number,
  data: PipelineUpdate
): Promise<Pipeline> => {
  const response = await apiClient.patch<Pipeline>(
    `${PIPELINES_BASE}/${pipelineId}`,
    data
  );
  return response.data;
};

/**
 * Delete a pipeline
 */
export const deletePipeline = async (pipelineId: number): Promise<void> => {
  await apiClient.delete(`${PIPELINES_BASE}/${pipelineId}`);
};

export const pipelinesApi = {
  list: listPipelines,
  get: getPipeline,
  create: createPipeline,
  update: updatePipeline,
  delete: deletePipeline,
};

export default pipelinesApi;

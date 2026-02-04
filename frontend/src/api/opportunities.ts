/**
 * Opportunities API
 */

import { apiClient } from './client';
import type {
  Opportunity,
  OpportunityCreate,
  OpportunityUpdate,
  OpportunityListResponse,
  OpportunityFilters,
  PipelineStage,
  PipelineStageCreate,
  PipelineStageUpdate,
  KanbanResponse,
  MoveOpportunityRequest,
  ForecastResponse,
  PipelineSummaryResponse,
} from '../types';

const OPPORTUNITIES_BASE = '/api/opportunities';

// =============================================================================
// Opportunities CRUD
// =============================================================================

/**
 * List opportunities with pagination and filters
 */
export const listOpportunities = async (
  filters: OpportunityFilters = {}
): Promise<OpportunityListResponse> => {
  const response = await apiClient.get<OpportunityListResponse>(OPPORTUNITIES_BASE, {
    params: filters,
  });
  return response.data;
};

/**
 * Get an opportunity by ID
 */
export const getOpportunity = async (opportunityId: number): Promise<Opportunity> => {
  const response = await apiClient.get<Opportunity>(
    `${OPPORTUNITIES_BASE}/${opportunityId}`
  );
  return response.data;
};

/**
 * Create a new opportunity
 */
export const createOpportunity = async (
  opportunityData: OpportunityCreate
): Promise<Opportunity> => {
  const response = await apiClient.post<Opportunity>(OPPORTUNITIES_BASE, opportunityData);
  return response.data;
};

/**
 * Update an opportunity
 */
export const updateOpportunity = async (
  opportunityId: number,
  opportunityData: OpportunityUpdate
): Promise<Opportunity> => {
  const response = await apiClient.patch<Opportunity>(
    `${OPPORTUNITIES_BASE}/${opportunityId}`,
    opportunityData
  );
  return response.data;
};

/**
 * Delete an opportunity
 */
export const deleteOpportunity = async (opportunityId: number): Promise<void> => {
  await apiClient.delete(`${OPPORTUNITIES_BASE}/${opportunityId}`);
};

// =============================================================================
// Pipeline Stages
// =============================================================================

/**
 * List all pipeline stages
 */
export const listStages = async (activeOnly = true): Promise<PipelineStage[]> => {
  const response = await apiClient.get<PipelineStage[]>(`${OPPORTUNITIES_BASE}/stages`, {
    params: { active_only: activeOnly },
  });
  return response.data;
};

/**
 * Create a new pipeline stage
 */
export const createStage = async (stageData: PipelineStageCreate): Promise<PipelineStage> => {
  const response = await apiClient.post<PipelineStage>(
    `${OPPORTUNITIES_BASE}/stages`,
    stageData
  );
  return response.data;
};

/**
 * Update a pipeline stage
 */
export const updateStage = async (
  stageId: number,
  stageData: PipelineStageUpdate
): Promise<PipelineStage> => {
  const response = await apiClient.patch<PipelineStage>(
    `${OPPORTUNITIES_BASE}/stages/${stageId}`,
    stageData
  );
  return response.data;
};

/**
 * Reorder pipeline stages
 */
export const reorderStages = async (
  stageOrders: Array<{ id: number; order: number }>
): Promise<PipelineStage[]> => {
  const response = await apiClient.post<PipelineStage[]>(
    `${OPPORTUNITIES_BASE}/stages/reorder`,
    stageOrders
  );
  return response.data;
};

// =============================================================================
// Kanban / Pipeline View
// =============================================================================

/**
 * Get Kanban board view of the pipeline
 */
export const getKanban = async (ownerId?: number): Promise<KanbanResponse> => {
  const response = await apiClient.get<KanbanResponse>(`${OPPORTUNITIES_BASE}/kanban`, {
    params: ownerId ? { owner_id: ownerId } : {},
  });
  return response.data;
};

/**
 * Move an opportunity to a different pipeline stage
 */
export const moveOpportunity = async (
  opportunityId: number,
  request: MoveOpportunityRequest
): Promise<Opportunity> => {
  const response = await apiClient.post<Opportunity>(
    `${OPPORTUNITIES_BASE}/${opportunityId}/move`,
    request
  );
  return response.data;
};

// =============================================================================
// Forecasting
// =============================================================================

/**
 * Get revenue forecast
 */
export const getForecast = async (
  monthsAhead = 6,
  ownerId?: number
): Promise<ForecastResponse> => {
  const response = await apiClient.get<ForecastResponse>(`${OPPORTUNITIES_BASE}/forecast`, {
    params: {
      months_ahead: monthsAhead,
      ...(ownerId && { owner_id: ownerId }),
    },
  });
  return response.data;
};

/**
 * Get pipeline summary
 */
export const getPipelineSummary = async (
  ownerId?: number
): Promise<PipelineSummaryResponse> => {
  const response = await apiClient.get<PipelineSummaryResponse>(
    `${OPPORTUNITIES_BASE}/pipeline-summary`,
    {
      params: ownerId ? { owner_id: ownerId } : {},
    }
  );
  return response.data;
};

// Export all opportunity functions
export const opportunitiesApi = {
  // CRUD
  list: listOpportunities,
  get: getOpportunity,
  create: createOpportunity,
  update: updateOpportunity,
  delete: deleteOpportunity,
  // Stages
  listStages,
  createStage,
  updateStage,
  reorderStages,
  // Kanban
  getKanban,
  moveOpportunity,
  // Forecasting
  getForecast,
  getPipelineSummary,
};

export default opportunitiesApi;

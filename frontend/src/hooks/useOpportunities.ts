/**
 * Opportunities hooks using the entity CRUD factory pattern.
 * Uses TanStack Query for data fetching and caching.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createEntityHooks, createQueryKeys } from './useEntityCRUD';
import { opportunitiesApi } from '../api/opportunities';
import { CACHE_TIMES } from '../config/queryConfig';
import type {
  Opportunity,
  OpportunityCreate,
  OpportunityUpdate,
  OpportunityFilters,
  PipelineStageCreate,
  PipelineStageUpdate,
} from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const opportunityKeys = createQueryKeys('opportunities');

export const pipelineKeys = {
  all: ['pipeline'] as const,
  stages: (activeOnly?: boolean) => [...pipelineKeys.all, 'stages', { activeOnly }] as const,
  kanban: (ownerId?: number) => [...pipelineKeys.all, 'kanban', { ownerId }] as const,
  forecast: (monthsAhead?: number, ownerId?: number) =>
    [...pipelineKeys.all, 'forecast', { monthsAhead, ownerId }] as const,
  summary: (ownerId?: number) => [...pipelineKeys.all, 'summary', { ownerId }] as const,
};

// =============================================================================
// Entity CRUD Hooks using Factory Pattern
// =============================================================================

const opportunityEntityHooks = createEntityHooks<
  Opportunity,
  OpportunityCreate,
  OpportunityUpdate,
  OpportunityFilters
>({
  entityName: 'opportunities',
  baseUrl: '/api/opportunities',
  queryKey: 'opportunities',
});

/**
 * Hook to fetch a paginated list of opportunities
 */
export function useOpportunities(filters?: OpportunityFilters) {
  return opportunityEntityHooks.useList(filters);
}

/**
 * Hook to fetch a single opportunity by ID
 */
export function useOpportunity(id: number | undefined) {
  return opportunityEntityHooks.useOne(id);
}

/**
 * Hook to create a new opportunity
 */
export function useCreateOpportunity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: OpportunityCreate) => opportunitiesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: opportunityKeys.lists() });
      queryClient.invalidateQueries({ queryKey: pipelineKeys.kanban() });
      queryClient.invalidateQueries({ queryKey: pipelineKeys.summary() });
    },
  });
}

/**
 * Hook to update an opportunity
 */
export function useUpdateOpportunity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: OpportunityUpdate }) =>
      opportunitiesApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: opportunityKeys.lists() });
      queryClient.invalidateQueries({ queryKey: opportunityKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: pipelineKeys.kanban() });
      queryClient.invalidateQueries({ queryKey: pipelineKeys.summary() });
    },
  });
}

/**
 * Hook to delete an opportunity
 */
export function useDeleteOpportunity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => opportunitiesApi.delete(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: opportunityKeys.lists() });
      queryClient.removeQueries({ queryKey: opportunityKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: pipelineKeys.kanban() });
      queryClient.invalidateQueries({ queryKey: pipelineKeys.summary() });
    },
  });
}

// =============================================================================
// Pipeline Stage Hooks
// =============================================================================

/**
 * Hook to fetch all pipeline stages
 */
export function usePipelineStages(activeOnly = true) {
  return useQuery({
    queryKey: pipelineKeys.stages(activeOnly),
    queryFn: () => opportunitiesApi.listStages(activeOnly),
    ...CACHE_TIMES.REFERENCE,
  });
}

/**
 * Hook to create a new pipeline stage
 */
export function useCreatePipelineStage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: PipelineStageCreate) => opportunitiesApi.createStage(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [...pipelineKeys.all, 'stages'] });
      queryClient.invalidateQueries({ queryKey: [...pipelineKeys.all, 'kanban'] });
    },
  });
}

/**
 * Hook to update a pipeline stage
 */
export function useUpdatePipelineStage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: PipelineStageUpdate }) =>
      opportunitiesApi.updateStage(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [...pipelineKeys.all, 'stages'] });
      queryClient.invalidateQueries({ queryKey: [...pipelineKeys.all, 'kanban'] });
    },
  });
}

/**
 * Hook to reorder pipeline stages
 */
export function useReorderPipelineStages() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (stageOrders: Array<{ id: number; order: number }>) =>
      opportunitiesApi.reorderStages(stageOrders),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [...pipelineKeys.all, 'stages'] });
      queryClient.invalidateQueries({ queryKey: [...pipelineKeys.all, 'kanban'] });
    },
  });
}

// =============================================================================
// Kanban / Pipeline View Hooks
// =============================================================================

/**
 * Hook to fetch Kanban board view of the pipeline
 */
export function useKanban(ownerId?: number) {
  return useQuery({
    queryKey: pipelineKeys.kanban(ownerId),
    queryFn: () => opportunitiesApi.getKanban(ownerId),
  });
}

/**
 * Hook to move an opportunity to a different pipeline stage
 */
export function useMoveOpportunity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      opportunityId,
      newStageId,
    }: {
      opportunityId: number;
      newStageId: number;
    }) => opportunitiesApi.moveOpportunity(opportunityId, { new_stage_id: newStageId }),
    onSuccess: (_, { opportunityId }) => {
      queryClient.invalidateQueries({ queryKey: pipelineKeys.kanban() });
      queryClient.invalidateQueries({ queryKey: opportunityKeys.detail(opportunityId) });
      queryClient.invalidateQueries({ queryKey: opportunityKeys.lists() });
    },
  });
}

// =============================================================================
// Forecasting Hooks
// =============================================================================

/**
 * Hook to fetch revenue forecast
 */
export function useForecast(monthsAhead = 6, ownerId?: number) {
  return useQuery({
    queryKey: pipelineKeys.forecast(monthsAhead, ownerId),
    queryFn: () => opportunitiesApi.getForecast(monthsAhead, ownerId),
  });
}

/**
 * Hook to fetch pipeline summary
 */
export function usePipelineSummary(ownerId?: number) {
  return useQuery({
    queryKey: pipelineKeys.summary(ownerId),
    queryFn: () => opportunitiesApi.getPipelineSummary(ownerId),
  });
}

// =============================================================================
// Search Hook
// =============================================================================

/**
 * Hook to search opportunities by name
 */
export function useOpportunitySearch(searchTerm: string, limit = 10) {
  return useQuery({
    queryKey: [...opportunityKeys.lists(), 'search', searchTerm],
    queryFn: async () => {
      const response = await opportunitiesApi.list({ search: searchTerm, page_size: limit });
      return response.items;
    },
    enabled: searchTerm.length >= 2,
  });
}

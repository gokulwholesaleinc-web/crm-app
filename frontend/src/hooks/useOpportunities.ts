import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createEntityHooks, createQueryKeys } from './useEntityCRUD';
import { opportunitiesApi } from '../api/opportunities';
import { CACHE_TIMES } from '../config/queryConfig';
import { showError } from '../utils/toast';
import type {
  Opportunity,
  OpportunityCreate,
  OpportunityUpdate,
  OpportunityFilters,
  PipelineStageCreate,
  PipelineStageUpdate,
  KanbanResponse,
} from '../types';

// Query Keys

export const opportunityKeys = createQueryKeys('opportunities');

export const pipelineKeys = {
  all: ['pipeline'] as const,
  stages: (activeOnly?: boolean, pipelineType?: string) => [...pipelineKeys.all, 'stages', { activeOnly, pipelineType }] as const,
  kanban: (ownerId?: number) => [...pipelineKeys.all, 'kanban', { ownerId }] as const,
  forecast: (monthsAhead?: number, ownerId?: number) =>
    [...pipelineKeys.all, 'forecast', { monthsAhead, ownerId }] as const,
  summary: (ownerId?: number) => [...pipelineKeys.all, 'summary', { ownerId }] as const,
};

// Entity CRUD Hooks using Factory Pattern

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

export function useOpportunities(filters?: OpportunityFilters) {
  return opportunityEntityHooks.useList(filters);
}

export function useOpportunity(id: number | undefined) {
  return opportunityEntityHooks.useOne(id);
}

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

// Pipeline Stage Hooks

export function usePipelineStages(activeOnly = true, pipelineType?: string) {
  return useQuery({
    queryKey: pipelineKeys.stages(activeOnly, pipelineType),
    queryFn: () => opportunitiesApi.listStages(activeOnly, pipelineType),
    ...CACHE_TIMES.REFERENCE,
  });
}

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

export function useDeletePipelineStage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (stageId: number) => opportunitiesApi.deleteStage(stageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [...pipelineKeys.all, 'stages'] });
      queryClient.invalidateQueries({ queryKey: [...pipelineKeys.all, 'kanban'] });
    },
  });
}

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

// Kanban / Pipeline View Hooks

export function useKanban(ownerId?: number) {
  return useQuery({
    queryKey: pipelineKeys.kanban(ownerId),
    queryFn: () => opportunitiesApi.getKanban(ownerId),
  });
}

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
    onMutate: async ({ opportunityId, newStageId }) => {
      await queryClient.cancelQueries({ queryKey: pipelineKeys.kanban() });
      const snapshot = queryClient.getQueryData<KanbanResponse>(pipelineKeys.kanban());
      if (snapshot) {
        const movingOpp = snapshot.stages.flatMap((s) => s.opportunities).find((o) => o.id === opportunityId);
        const optimistic: KanbanResponse = {
          stages: snapshot.stages.map((stage) => {
            const hasOpp = stage.opportunities.some((o) => o.id === opportunityId);
            if (hasOpp && stage.stage_id !== newStageId) {
              return {
                ...stage,
                opportunities: stage.opportunities.filter((o) => o.id !== opportunityId),
                count: stage.count - 1,
                total_amount: stage.total_amount - (movingOpp?.amount ?? 0),
                total_weighted: stage.total_weighted - (movingOpp?.weighted_amount ?? 0),
              };
            }
            if (!hasOpp && stage.stage_id === newStageId && movingOpp) {
              return {
                ...stage,
                opportunities: [...stage.opportunities, movingOpp],
                count: stage.count + 1,
                total_amount: stage.total_amount + (movingOpp.amount ?? 0),
                total_weighted: stage.total_weighted + (movingOpp.weighted_amount ?? 0),
              };
            }
            return stage;
          }),
        };
        queryClient.setQueryData(pipelineKeys.kanban(), optimistic);
      }
      return { snapshot };
    },
    onError: (_err, _vars, context) => {
      if (context?.snapshot) {
        queryClient.setQueryData(pipelineKeys.kanban(), context.snapshot);
      }
      showError('Failed to move opportunity — change has been reverted.');
    },
    onSettled: (_data, _err, { opportunityId }) => {
      queryClient.invalidateQueries({ queryKey: pipelineKeys.kanban() });
      queryClient.invalidateQueries({ queryKey: opportunityKeys.detail(opportunityId) });
      queryClient.invalidateQueries({ queryKey: opportunityKeys.lists() });
    },
  });
}

// Forecasting Hooks

export function useForecast(monthsAhead = 6, ownerId?: number) {
  return useQuery({
    queryKey: pipelineKeys.forecast(monthsAhead, ownerId),
    queryFn: () => opportunitiesApi.getForecast(monthsAhead, ownerId),
  });
}

export function usePipelineSummary(ownerId?: number) {
  return useQuery({
    queryKey: pipelineKeys.summary(ownerId),
    queryFn: () => opportunitiesApi.getPipelineSummary(ownerId),
  });
}

// Search Hook

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

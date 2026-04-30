import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createEntityHooks, createQueryKeys } from './useEntityCRUD';
import { leadsApi } from '../api/leads';
import type { SendCampaignRequest } from '../api/leads';
import { contactKeys } from './useContacts';
import { companyKeys } from './useCompanies';
import { opportunityKeys } from './useOpportunities';
import { CACHE_TIMES } from '../config/queryConfig';
import { showError } from '../utils/toast';
import type {
  Lead,
  LeadCreate,
  LeadUpdate,
  LeadFilters,
  LeadSourceCreate,
  LeadSourceUpdate,
  LeadConvertToContactRequest,
  LeadConvertToOpportunityRequest,
  LeadFullConversionRequest,
  LeadKanbanResponse,
} from '../types';

// Query Keys

export const leadKeys = createQueryKeys('leads');

export const leadSourceKeys = {
  all: ['lead-sources'] as const,
  list: (activeOnly?: boolean) => [...leadSourceKeys.all, 'list', { activeOnly }] as const,
};

// Entity CRUD Hooks using Factory Pattern

const leadEntityHooks = createEntityHooks<
  Lead,
  LeadCreate,
  LeadUpdate,
  LeadFilters
>({
  entityName: 'leads',
  baseUrl: '/api/leads',
  queryKey: 'leads',
});

export function useLeads(
  filters?: LeadFilters,
  options?: Parameters<typeof leadEntityHooks.useList>[1]
) {
  return leadEntityHooks.useList(filters, options);
}

export function useLead(id: number | undefined) {
  return leadEntityHooks.useOne(id);
}

export function useCreateLead() {
  return leadEntityHooks.useCreate();
}

export function useUpdateLead() {
  return leadEntityHooks.useUpdate();
}

export function useDeleteLead() {
  return leadEntityHooks.useDelete();
}

// Lead Conversion Hooks

export function useConvertLeadToContact() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ leadId, data }: { leadId: number; data: LeadConvertToContactRequest }) =>
      leadsApi.convertToContact(leadId, data),
    onSuccess: (_, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
      queryClient.invalidateQueries({ queryKey: contactKeys.lists() });
      queryClient.invalidateQueries({ queryKey: companyKeys.lists() });
    },
  });
}

export function useConvertLeadToOpportunity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ leadId, data }: { leadId: number; data: LeadConvertToOpportunityRequest }) =>
      leadsApi.convertToOpportunity(leadId, data),
    onSuccess: (_, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
      queryClient.invalidateQueries({ queryKey: opportunityKeys.lists() });
    },
  });
}

export function useConvertLead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ leadId, data }: { leadId: number; data: LeadFullConversionRequest }) =>
      leadsApi.fullConversion(leadId, data),
    onSuccess: (_, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
      queryClient.invalidateQueries({ queryKey: contactKeys.lists() });
      queryClient.invalidateQueries({ queryKey: companyKeys.lists() });
      queryClient.invalidateQueries({ queryKey: opportunityKeys.lists() });
    },
  });
}

// Lead Source Hooks

export function useLeadSources(activeOnly = true) {
  return useQuery({
    queryKey: leadSourceKeys.list(activeOnly),
    queryFn: () => leadsApi.listSources(activeOnly),
    ...CACHE_TIMES.REFERENCE,
  });
}

export function useCreateLeadSource() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: LeadSourceCreate) => leadsApi.createSource(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leadSourceKeys.all });
    },
  });
}

export function useUpdateLeadSource() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: LeadSourceUpdate }) =>
      leadsApi.updateSource(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leadSourceKeys.all });
      // Lead detail/list views render the source name — refresh them too
      // so a rename propagates without a full reload.
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
    },
  });
}

export function useDeleteLeadSource() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => leadsApi.deleteSource(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leadSourceKeys.all });
    },
  });
}

// Lead Pipeline / Kanban Hooks

export const leadPipelineKeys = {
  all: ['lead-pipeline'] as const,
  stages: () => [...leadPipelineKeys.all, 'stages'] as const,
  kanban: (ownerId?: number) => [...leadPipelineKeys.all, 'kanban', { ownerId }] as const,
};

export function useLeadPipelineStages() {
  return useQuery({
    queryKey: leadPipelineKeys.stages(),
    queryFn: () => leadsApi.getLeadPipelineStages(),
    ...CACHE_TIMES.REFERENCE,
  });
}

export function useLeadKanban(ownerId?: number) {
  return useQuery({
    queryKey: leadPipelineKeys.kanban(ownerId),
    queryFn: () => leadsApi.getLeadKanban(ownerId),
  });
}

export function useMoveLeadStage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      leadId,
      newStageId,
    }: {
      leadId: number;
      newStageId: number;
    }) => leadsApi.moveLeadStage(leadId, { new_stage_id: newStageId }),
    onMutate: async ({ leadId, newStageId }) => {
      await queryClient.cancelQueries({ queryKey: leadPipelineKeys.kanban() });
      const snapshot = queryClient.getQueryData<LeadKanbanResponse>(leadPipelineKeys.kanban());
      if (snapshot) {
        const optimistic: LeadKanbanResponse = {
          stages: snapshot.stages.map((stage) => {
            const lead = stage.leads.find((l) => l.id === leadId);
            if (lead && stage.stage_id !== newStageId) {
              return { ...stage, leads: stage.leads.filter((l) => l.id !== leadId), count: stage.count - 1 };
            }
            if (!lead && stage.stage_id === newStageId) {
              const movingLead = snapshot.stages.flatMap((s) => s.leads).find((l) => l.id === leadId);
              if (movingLead) {
                return { ...stage, leads: [...stage.leads, movingLead], count: stage.count + 1 };
              }
            }
            return stage;
          }),
        };
        queryClient.setQueryData(leadPipelineKeys.kanban(), optimistic);
      }
      return { snapshot };
    },
    onError: (_err, _vars, context) => {
      if (context?.snapshot) {
        queryClient.setQueryData(leadPipelineKeys.kanban(), context.snapshot);
      }
      showError('Failed to move lead — change has been reverted.');
    },
    onSettled: (_data, _err, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadPipelineKeys.kanban() });
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
    },
    onSuccess: (data) => {
      if (data.conversion) {
        queryClient.invalidateQueries({ queryKey: opportunityKeys.lists() });
        queryClient.invalidateQueries({ queryKey: contactKeys.lists() });
        queryClient.invalidateQueries({ queryKey: companyKeys.lists() });
        queryClient.invalidateQueries({ queryKey: ['unified-pipeline'] });
        queryClient.invalidateQueries({ queryKey: ['pipeline'] });
      }
    },
  });
}

// Email Campaign Hooks

export function useSendCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SendCampaignRequest) => leadsApi.sendCampaign(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
    },
  });
}

// Search Hook

export function useLeadSearch(searchTerm: string, limit = 10) {
  return useQuery({
    queryKey: [...leadKeys.lists(), 'search', searchTerm],
    queryFn: async () => {
      const response = await leadsApi.list({ search: searchTerm, page_size: limit });
      return response.items;
    },
    enabled: searchTerm.length >= 2,
  });
}

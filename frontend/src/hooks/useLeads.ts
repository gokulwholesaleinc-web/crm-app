/**
 * Leads hooks using the entity CRUD factory pattern.
 * Uses TanStack Query for data fetching and caching.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createEntityHooks, createQueryKeys } from './useEntityCRUD';
import { leadsApi } from '../api/leads';
import { contactKeys } from './useContacts';
import { companyKeys } from './useCompanies';
import { opportunityKeys } from './useOpportunities';
import { CACHE_TIMES } from '../config/queryConfig';
import type {
  Lead,
  LeadCreate,
  LeadUpdate,
  LeadFilters,
  LeadSourceCreate,
  LeadConvertToContactRequest,
  LeadConvertToOpportunityRequest,
  LeadFullConversionRequest,
} from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const leadKeys = createQueryKeys('leads');

export const leadSourceKeys = {
  all: ['lead-sources'] as const,
  list: (activeOnly?: boolean) => [...leadSourceKeys.all, 'list', { activeOnly }] as const,
};

// =============================================================================
// Entity CRUD Hooks using Factory Pattern
// =============================================================================

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

/**
 * Hook to fetch a paginated list of leads
 */
export function useLeads(filters?: LeadFilters) {
  return leadEntityHooks.useList(filters);
}

/**
 * Hook to fetch a single lead by ID
 */
export function useLead(id: number | undefined) {
  return leadEntityHooks.useOne(id);
}

/**
 * Hook to create a new lead
 */
export function useCreateLead() {
  return leadEntityHooks.useCreate();
}

/**
 * Hook to update a lead
 */
export function useUpdateLead() {
  return leadEntityHooks.useUpdate();
}

/**
 * Hook to delete a lead
 */
export function useDeleteLead() {
  return leadEntityHooks.useDelete();
}

// =============================================================================
// Lead Conversion Hooks
// =============================================================================

/**
 * Hook to convert a lead to a contact
 */
export function useConvertLeadToContact() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ leadId, data }: { leadId: number; data: LeadConvertToContactRequest }) =>
      leadsApi.convertToContact(leadId, data),
    onSuccess: (_, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
      // Also invalidate contacts as a new one was created
      queryClient.invalidateQueries({ queryKey: contactKeys.lists() });
      // Invalidate companies if a company was created
      queryClient.invalidateQueries({ queryKey: companyKeys.lists() });
    },
  });
}

/**
 * Hook to convert a lead to an opportunity
 */
export function useConvertLeadToOpportunity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ leadId, data }: { leadId: number; data: LeadConvertToOpportunityRequest }) =>
      leadsApi.convertToOpportunity(leadId, data),
    onSuccess: (_, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
      // Also invalidate opportunities as a new one was created
      queryClient.invalidateQueries({ queryKey: opportunityKeys.lists() });
    },
  });
}

/**
 * Hook for full lead conversion: Lead -> Contact + Company + Opportunity
 */
export function useConvertLead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ leadId, data }: { leadId: number; data: LeadFullConversionRequest }) =>
      leadsApi.fullConversion(leadId, data),
    onSuccess: (_, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
      // Invalidate all related entities
      queryClient.invalidateQueries({ queryKey: contactKeys.lists() });
      queryClient.invalidateQueries({ queryKey: companyKeys.lists() });
      queryClient.invalidateQueries({ queryKey: opportunityKeys.lists() });
    },
  });
}

// =============================================================================
// Lead Source Hooks
// =============================================================================

/**
 * Hook to fetch all lead sources
 */
export function useLeadSources(activeOnly = true) {
  return useQuery({
    queryKey: leadSourceKeys.list(activeOnly),
    queryFn: () => leadsApi.listSources(activeOnly),
    ...CACHE_TIMES.REFERENCE,
  });
}

/**
 * Hook to create a new lead source
 */
export function useCreateLeadSource() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: LeadSourceCreate) => leadsApi.createSource(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leadSourceKeys.all });
    },
  });
}

// =============================================================================
// Lead Pipeline / Kanban Hooks
// =============================================================================

export const leadPipelineKeys = {
  all: ['lead-pipeline'] as const,
  stages: () => [...leadPipelineKeys.all, 'stages'] as const,
  kanban: (ownerId?: number) => [...leadPipelineKeys.all, 'kanban', { ownerId }] as const,
};

/**
 * Hook to fetch lead pipeline stages
 */
export function useLeadPipelineStages() {
  return useQuery({
    queryKey: leadPipelineKeys.stages(),
    queryFn: () => leadsApi.getLeadPipelineStages(),
    ...CACHE_TIMES.REFERENCE,
  });
}

/**
 * Hook to fetch lead Kanban board data
 */
export function useLeadKanban(ownerId?: number) {
  return useQuery({
    queryKey: leadPipelineKeys.kanban(ownerId),
    queryFn: () => leadsApi.getLeadKanban(ownerId),
  });
}

/**
 * Hook to move a lead to a different pipeline stage
 */
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
    onSuccess: (data, { leadId }) => {
      queryClient.invalidateQueries({ queryKey: leadPipelineKeys.kanban() });
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(leadId) });
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
      // If auto-conversion happened, invalidate opportunity and contact caches too
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

// =============================================================================
// Search Hook
// =============================================================================

/**
 * Hook to search leads by name or email
 */
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

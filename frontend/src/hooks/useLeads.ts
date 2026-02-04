/**
 * Leads hooks using TanStack Query
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { leadsApi } from '../api/leads';
import { contactKeys } from './useContacts';
import { companyKeys } from './useCompanies';
import { opportunityKeys } from './useOpportunities';
import type {
  LeadCreate,
  LeadUpdate,
  LeadFilters,
  LeadSourceCreate,
  LeadConvertToContactRequest,
  LeadConvertToOpportunityRequest,
  LeadFullConversionRequest,
} from '../types';

// Query keys
export const leadKeys = {
  all: ['leads'] as const,
  lists: () => [...leadKeys.all, 'list'] as const,
  list: (filters?: LeadFilters) => [...leadKeys.lists(), filters] as const,
  details: () => [...leadKeys.all, 'detail'] as const,
  detail: (id: number) => [...leadKeys.details(), id] as const,
};

export const leadSourceKeys = {
  all: ['lead-sources'] as const,
  list: (activeOnly?: boolean) => [...leadSourceKeys.all, 'list', { activeOnly }] as const,
};

// =============================================================================
// Lead CRUD Hooks
// =============================================================================

/**
 * Hook to fetch a paginated list of leads
 */
export function useLeads(filters?: LeadFilters) {
  return useQuery({
    queryKey: leadKeys.list(filters),
    queryFn: () => leadsApi.list(filters),
  });
}

/**
 * Hook to fetch a single lead by ID
 */
export function useLead(id: number | undefined) {
  return useQuery({
    queryKey: leadKeys.detail(id!),
    queryFn: () => leadsApi.get(id!),
    enabled: !!id,
  });
}

/**
 * Hook to create a new lead
 */
export function useCreateLead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: LeadCreate) => leadsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
    },
  });
}

/**
 * Hook to update a lead
 */
export function useUpdateLead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: LeadUpdate }) => leadsApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
      queryClient.invalidateQueries({ queryKey: leadKeys.detail(id) });
    },
  });
}

/**
 * Hook to delete a lead
 */
export function useDeleteLead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => leadsApi.delete(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
      queryClient.removeQueries({ queryKey: leadKeys.detail(id) });
    },
  });
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
    staleTime: 10 * 60 * 1000, // 10 minutes - sources don't change often
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

/**
 * Proposals hooks using TanStack Query.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createEntityHooks, createQueryKeys } from './useEntityCRUD';
import { proposalsApi } from '../api/proposals';
import { useAuthQuery } from './useAuthQuery';
import type {
  Proposal,
  ProposalCreate,
  ProposalUpdate,
  ProposalFilters,
  ProposalTemplate,
  AIGenerateProposalRequest,
} from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const proposalKeys = createQueryKeys('proposals');

// =============================================================================
// Entity CRUD Hooks using Factory Pattern
// =============================================================================

const proposalEntityHooks = createEntityHooks<
  Proposal,
  ProposalCreate,
  ProposalUpdate,
  ProposalFilters
>({
  entityName: 'proposals',
  baseUrl: '/api/proposals',
  queryKey: 'proposals',
});

/**
 * Hook to fetch a paginated list of proposals
 */
export function useProposals(filters?: ProposalFilters) {
  return proposalEntityHooks.useList(filters);
}

/**
 * Hook to fetch a single proposal by ID
 */
export function useProposal(id: number | undefined) {
  return proposalEntityHooks.useOne(id);
}

/**
 * Hook to create a new proposal
 */
export function useCreateProposal() {
  return proposalEntityHooks.useCreate();
}

/**
 * Hook to update a proposal
 */
export function useUpdateProposal() {
  return proposalEntityHooks.useUpdate();
}

/**
 * Hook to delete a proposal
 */
export function useDeleteProposal() {
  return proposalEntityHooks.useDelete();
}

// =============================================================================
// Status Action Hooks
// =============================================================================

/**
 * Hook to send a proposal
 */
export function useSendProposal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (proposalId: number) => proposalsApi.send(proposalId),
    onSuccess: (_data, proposalId) => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
      queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposalId) });
    },
  });
}

/**
 * Hook to accept a proposal
 */
export function useAcceptProposal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (proposalId: number) => proposalsApi.accept(proposalId),
    onSuccess: (_data, proposalId) => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
      queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposalId) });
    },
  });
}

/**
 * Hook to reject a proposal
 */
export function useRejectProposal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (proposalId: number) => proposalsApi.reject(proposalId),
    onSuccess: (_data, proposalId) => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
      queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposalId) });
    },
  });
}

// =============================================================================
// AI Generation Hook
// =============================================================================

/**
 * Hook to generate a proposal using AI
 */
export function useGenerateProposal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: AIGenerateProposalRequest) => proposalsApi.generate(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
    },
  });
}

// =============================================================================
// Template Hooks
// =============================================================================

/**
 * Hook to fetch proposal templates
 */
export function useProposalTemplates() {
  return useAuthQuery({
    queryKey: ['proposals', 'templates'],
    queryFn: () => proposalsApi.listTemplates(),
  });
}

/**
 * Hook to create a proposal template
 */
export function useCreateProposalTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: proposalsApi.createTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proposals', 'templates'] });
    },
  });
}

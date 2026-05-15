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
  ProposalTemplateCreate,
  ProposalTemplateUpdate,
  CreateFromTemplateRequest,
  SignatureFieldCoords,
} from '../types';

// Query Keys

export const proposalKeys = createQueryKeys('proposals');

// Entity CRUD Hooks using Factory Pattern

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
 * Hook to fetch a single proposal by ID.
 *
 * While the proposal is awaiting customer action (``sent`` or ``viewed``)
 * we poll every 20 s so the CRM detail view auto-flips to "Accepted" the
 * moment the signer signs, with no manual refresh. Polling pauses
 * automatically once the status moves out of those two states.
 */
export function useProposal(id: number | undefined) {
  return proposalEntityHooks.useOne(id, {
    refetchInterval: (query) => {
      const status = (query.state.data as Proposal | undefined)?.status;
      return status === 'sent' || status === 'viewed' ? 20_000 : false;
    },
  });
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

// Status Action Hooks

/**
 * Hook to send a proposal with branded email
 */
export function useSendProposal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ proposalId, attachPdf = false }: { proposalId: number; attachPdf?: boolean }) =>
      proposalsApi.sendWithEmail(proposalId, attachPdf),
    onSuccess: (_data, { proposalId }) => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
      queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposalId) });
    },
  });
}

/**
 * Download a branded proposal PDF and trigger browser download
 */
export function useDownloadProposalPDF() {
  return async (proposalId: number, proposalNumber: string) => {
    const blob = await proposalsApi.downloadPDF(proposalId);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `proposal-${proposalNumber}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };
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

export function useResendProposalPaymentLink() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (proposalId: number) => proposalsApi.resendPaymentLink(proposalId),
    onSuccess: (_data, proposalId) => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposalId) });
    },
  });
}

export function useRetryProposalBilling() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (proposalId: number) => proposalsApi.retryBilling(proposalId),
    onSuccess: (_data, proposalId) => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
      queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposalId) });
    },
  });
}

/**
 * PATCH a proposal's saved signature-box placement.
 *
 * Wraps ``proposalsApi.update`` so the call site reads as what it
 * does — the visual picker is the only place this field is written
 * from. Pass ``null`` to clear back to the auto-box default.
 */
export function useUpdateProposalSignatureCoords() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      proposalId,
      coords,
    }: {
      proposalId: number;
      coords: SignatureFieldCoords | null;
    }) =>
      proposalsApi.update(proposalId, { signature_field_coords: coords }),
    onSuccess: (_data, { proposalId }) => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
      queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposalId) });
    },
  });
}

export function useRestampProposalSignedPdf() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (proposalId: number) => proposalsApi.restampSignedPdf(proposalId),
    onSuccess: (_data, proposalId) => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposalId) });
    },
  });
}

// ``useRefreshProposalFromQuote`` removed 2026-05-14 — quotes router
// unmounted; corresponding endpoint dropped from the backend.

// Template Hooks

/**
 * Hook to fetch proposal templates
 */
export function useProposalTemplates(category?: string) {
  return useAuthQuery({
    queryKey: ['proposals', 'templates', category],
    queryFn: () => proposalsApi.listTemplates(category),
  });
}

/**
 * Hook to fetch a single proposal template
 */
export function useProposalTemplate(id: number | undefined) {
  return useAuthQuery({
    queryKey: ['proposals', 'templates', id],
    queryFn: () => proposalsApi.getTemplate(id!),
    enabled: !!id,
  });
}

/**
 * Hook to create a proposal template
 */
export function useCreateProposalTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ProposalTemplateCreate) => proposalsApi.createTemplate(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proposals', 'templates'] });
    },
  });
}

/**
 * Hook to update a proposal template
 */
export function useUpdateProposalTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ProposalTemplateUpdate }) =>
      proposalsApi.updateTemplate(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proposals', 'templates'] });
    },
  });
}

/**
 * Hook to delete a proposal template
 */
export function useDeleteProposalTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => proposalsApi.deleteTemplate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['proposals', 'templates'] });
    },
  });
}

/**
 * Hook to create a proposal from a template
 */
export function useCreateFromTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateFromTemplateRequest) => proposalsApi.createFromTemplate(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
    },
  });
}

/**
 * Hook to duplicate a proposal as a new draft.
 */
export function useDuplicateProposal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (proposalId: number) => proposalsApi.duplicate(proposalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
    },
  });
}

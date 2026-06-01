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
  ProposalBundleCreate,
  ProposalBundleUpdate,
  ProposalTemplateCreate,
  ProposalTemplateUpdate,
  CreateFromTemplateRequest,
  SignatureFieldCoordsValue,
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
 * Hook to accept a proposal (internal/admin offline-acceptance path).
 *
 * ``acknowledgeUnsigned`` is forwarded to the backend's manual-confirmation
 * guard: omit it on the first attempt and, if the proposal has an unsigned
 * signature target, the call rejects with 409 so the UI can confirm and
 * re-submit with the acknowledgement.
 */
export function useAcceptProposal() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      proposalId,
      acknowledgeUnsigned = false,
    }: {
      proposalId: number;
      acknowledgeUnsigned?: boolean;
    }) => proposalsApi.accept(proposalId, acknowledgeUnsigned),
    onSuccess: (_data, { proposalId }) => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
      queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposalId) });
    },
  });
}

export function useProposalBundle(bundleId: number | undefined) {
  return useAuthQuery({
    queryKey: ['proposal-bundles', bundleId],
    queryFn: () => proposalsApi.getBundle(bundleId!),
    enabled: Boolean(bundleId),
  });
}

export function useCreateProposalBundle() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ProposalBundleCreate) => proposalsApi.createBundle(data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
      for (const proposal of data.proposals ?? []) {
        queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposal.id) });
      }
    },
  });
}

export function useUpdateProposalBundle() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      bundleId,
      data,
    }: {
      bundleId: number;
      data: ProposalBundleUpdate;
    }) => proposalsApi.updateBundle(bundleId, data),
    onSuccess: (data, { bundleId }) => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
      queryClient.invalidateQueries({ queryKey: ['proposal-bundles', bundleId] });
      for (const proposal of data.proposals ?? []) {
        queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposal.id) });
      }
    },
  });
}

export function useSendProposalBundle() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (bundleId: number) => proposalsApi.sendBundle(bundleId),
    onSuccess: (data, bundleId) => {
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
      queryClient.invalidateQueries({ queryKey: ['proposal-bundles', bundleId] });
      for (const proposal of data.proposals ?? []) {
        queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposal.id) });
      }
    },
  });
}

/**
 * Remove a single option from a draft bundle. Returns null when the
 * removal dissolved the bundle — callers must handle navigation in that
 * case because the proposal page they were on may no longer make sense.
 */
export function useRemoveProposalBundleOption() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ bundleId, proposalId }: { bundleId: number; proposalId: number }) =>
      proposalsApi.removeBundleOption(bundleId, proposalId),
    onSuccess: (data, { bundleId, proposalId }) => {
      // List page changes regardless of dissolve vs shrink — invalidate.
      queryClient.invalidateQueries({ queryKey: proposalKeys.lists() });
      queryClient.invalidateQueries({ queryKey: ['proposal-bundles', bundleId] });
      // The removed proposal's detail row now has bundle_id=null — refetch.
      queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposalId) });
      if (data) {
        for (const proposal of data.proposals ?? []) {
          queryClient.invalidateQueries({ queryKey: proposalKeys.detail(proposal.id) });
        }
      }
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
      dateCoords,
    }: {
      proposalId: number;
      coords: SignatureFieldCoordsValue | null;
      dateCoords?: SignatureFieldCoordsValue | null;
    }) =>
      proposalsApi.update(proposalId, {
        signature_field_coords: coords,
        date_field_coords: dateCoords,
      }),
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

/**
 * Contracts hooks using the entity CRUD factory pattern.
 * Uses TanStack Query for data fetching and caching.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createEntityHooks, createQueryKeys } from './useEntityCRUD';
import { contractsApi, sendContract, getContractStats } from '../api/contracts';
import type {
  Contract,
  ContractCreate,
  ContractUpdate,
  ContractFilters,
} from '../types';

// Query Keys

export const contractKeys = createQueryKeys('contracts');

// Entity CRUD Hooks using Factory Pattern

const contractEntityHooks = createEntityHooks<
  Contract,
  ContractCreate,
  ContractUpdate,
  ContractFilters
>({
  entityName: 'contracts',
  baseUrl: '/api/contracts',
  queryKey: 'contracts',
});

/**
 * Hook to fetch a paginated list of contracts
 */
export function useContracts(filters?: ContractFilters) {
  return contractEntityHooks.useList(filters);
}

/**
 * Hook to fetch a single contract by ID.
 *
 * While the contract is ``sent`` (awaiting signer action) we poll every
 * 20 s so the CRM detail view auto-flips to "Signed" the moment the
 * customer signs, with no manual refresh. Polling pauses automatically
 * once the status moves out of ``sent``.
 */
export function useContract(id: number | undefined) {
  return contractEntityHooks.useOne(id, {
    refetchInterval: (query) => {
      const status = (query.state.data as Contract | undefined)?.status;
      return status === 'sent' ? 20_000 : false;
    },
  });
}

/**
 * Hook to create a new contract
 */
export function useCreateContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ContractCreate) => contractsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: contractKeys.lists() });
    },
  });
}

/**
 * Hook to update a contract
 */
export function useUpdateContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ContractUpdate }) =>
      contractsApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: contractKeys.lists() });
      queryClient.invalidateQueries({ queryKey: contractKeys.detail(id) });
    },
  });
}

/**
 * Hook to delete a contract
 */
export function useDeleteContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => contractsApi.delete(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: contractKeys.lists() });
      queryClient.removeQueries({ queryKey: contractKeys.detail(id) });
    },
  });
}

/**
 * Hook to send a contract for signature
 */
export function useSendContract() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, body }: { id: number; body?: { to_email?: string; message?: string } }) =>
      sendContract(id, body),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: contractKeys.lists() });
      queryClient.invalidateQueries({ queryKey: contractKeys.detail(id) });
    },
  });
}

/**
 * Hook to fetch contract aggregate stats for the dashboard
 */
export function useContractStats() {
  return useQuery({
    queryKey: ['contracts', 'stats'],
    queryFn: getContractStats,
  });
}

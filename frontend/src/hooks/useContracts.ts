/**
 * Contracts hooks using the entity CRUD factory pattern.
 * Uses TanStack Query for data fetching and caching.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createEntityHooks, createQueryKeys } from './useEntityCRUD';
import { contractsApi } from '../api/contracts';
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
 * Hook to fetch a single contract by ID
 */
export function useContract(id: number | undefined) {
  return contractEntityHooks.useOne(id);
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

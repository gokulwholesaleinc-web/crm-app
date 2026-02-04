/**
 * Companies hooks using TanStack Query
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { companiesApi } from '../api/companies';
import type { CompanyCreate, CompanyUpdate, CompanyFilters } from '../types';

// Query keys
export const companyKeys = {
  all: ['companies'] as const,
  lists: () => [...companyKeys.all, 'list'] as const,
  list: (filters?: CompanyFilters) => [...companyKeys.lists(), filters] as const,
  details: () => [...companyKeys.all, 'detail'] as const,
  detail: (id: number) => [...companyKeys.details(), id] as const,
};

/**
 * Hook to fetch a paginated list of companies
 */
export function useCompanies(filters?: CompanyFilters) {
  return useQuery({
    queryKey: companyKeys.list(filters),
    queryFn: () => companiesApi.list(filters),
  });
}

/**
 * Hook to fetch a single company by ID
 */
export function useCompany(id: number | undefined) {
  return useQuery({
    queryKey: companyKeys.detail(id!),
    queryFn: () => companiesApi.get(id!),
    enabled: !!id,
  });
}

/**
 * Hook to create a new company
 */
export function useCreateCompany() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CompanyCreate) => companiesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: companyKeys.lists() });
    },
  });
}

/**
 * Hook to update a company
 */
export function useUpdateCompany() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: CompanyUpdate }) =>
      companiesApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: companyKeys.lists() });
      queryClient.invalidateQueries({ queryKey: companyKeys.detail(id) });
    },
  });
}

/**
 * Hook to delete a company
 */
export function useDeleteCompany() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => companiesApi.delete(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: companyKeys.lists() });
      queryClient.removeQueries({ queryKey: companyKeys.detail(id) });
    },
  });
}

/**
 * Hook to search companies by name
 */
export function useCompanySearch(searchTerm: string, limit = 10) {
  return useQuery({
    queryKey: [...companyKeys.lists(), 'search', searchTerm],
    queryFn: async () => {
      const response = await companiesApi.list({ search: searchTerm, page_size: limit });
      return response.items;
    },
    enabled: searchTerm.length >= 2,
  });
}

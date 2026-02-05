/**
 * Companies hooks using the entity CRUD factory pattern.
 * Uses TanStack Query for data fetching and caching.
 */

import { useQuery } from '@tanstack/react-query';
import { createEntityHooks, createQueryKeys } from './useEntityCRUD';
import { companiesApi } from '../api/companies';
import type { Company, CompanyCreate, CompanyUpdate, CompanyFilters } from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const companyKeys = createQueryKeys('companies');

// =============================================================================
// Entity CRUD Hooks using Factory Pattern
// =============================================================================

const companyEntityHooks = createEntityHooks<
  Company,
  CompanyCreate,
  CompanyUpdate,
  CompanyFilters
>({
  entityName: 'companies',
  baseUrl: '/api/companies',
  queryKey: 'companies',
});

/**
 * Hook to fetch a paginated list of companies
 */
export function useCompanies(filters?: CompanyFilters) {
  return companyEntityHooks.useList(filters);
}

/**
 * Hook to fetch a single company by ID
 */
export function useCompany(id: number | undefined) {
  return companyEntityHooks.useOne(id);
}

/**
 * Hook to create a new company
 */
export function useCreateCompany() {
  return companyEntityHooks.useCreate();
}

/**
 * Hook to update a company
 */
export function useUpdateCompany() {
  return companyEntityHooks.useUpdate();
}

/**
 * Hook to delete a company
 */
export function useDeleteCompany() {
  return companyEntityHooks.useDelete();
}

// =============================================================================
// Additional Specialized Hooks
// =============================================================================

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

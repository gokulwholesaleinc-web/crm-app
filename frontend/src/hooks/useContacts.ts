/**
 * Contacts hooks using the entity CRUD factory pattern.
 * Uses TanStack Query for data fetching and caching.
 */

import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { createEntityHooks, createQueryKeys, PaginatedResponse } from './useEntityCRUD';
import { contactsApi } from '../api/contacts';
import type { Contact, ContactCreate, ContactUpdate, ContactFilters } from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const contactKeys = createQueryKeys('contacts');

// =============================================================================
// Entity CRUD Hooks using Factory Pattern
// =============================================================================

const contactEntityHooks = createEntityHooks<
  Contact,
  ContactCreate,
  ContactUpdate,
  ContactFilters
>({
  entityName: 'contacts',
  baseUrl: '/api/contacts',
  queryKey: 'contacts',
});

/**
 * Hook to fetch a paginated list of contacts
 */
export function useContacts(
  filters?: ContactFilters,
  options?: Omit<UseQueryOptions<PaginatedResponse<Contact>>, 'queryKey' | 'queryFn'>
) {
  return contactEntityHooks.useList(filters, options);
}

/**
 * Hook to fetch a single contact by ID
 */
export function useContact(id: number | undefined) {
  return contactEntityHooks.useOne(id);
}

/**
 * Hook to create a new contact
 */
export function useCreateContact() {
  return contactEntityHooks.useCreate();
}

/**
 * Hook to update a contact
 */
export function useUpdateContact() {
  return contactEntityHooks.useUpdate();
}

/**
 * Hook to delete a contact
 */
export function useDeleteContact() {
  return contactEntityHooks.useDelete();
}

// =============================================================================
// Additional Specialized Hooks
// =============================================================================

/**
 * Hook to search contacts by name or email
 */
export function useContactSearch(searchTerm: string, limit = 10) {
  return useQuery({
    queryKey: [...contactKeys.lists(), 'search', searchTerm],
    queryFn: async () => {
      const response = await contactsApi.list({ search: searchTerm, page_size: limit });
      return response.items;
    },
    enabled: searchTerm.length >= 2,
  });
}

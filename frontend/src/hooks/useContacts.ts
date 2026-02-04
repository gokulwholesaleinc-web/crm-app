/**
 * Contacts hooks using TanStack Query
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { contactsApi } from '../api/contacts';
import type { ContactCreate, ContactUpdate, ContactFilters } from '../types';

// Query keys
export const contactKeys = {
  all: ['contacts'] as const,
  lists: () => [...contactKeys.all, 'list'] as const,
  list: (filters?: ContactFilters) => [...contactKeys.lists(), filters] as const,
  details: () => [...contactKeys.all, 'detail'] as const,
  detail: (id: number) => [...contactKeys.details(), id] as const,
};

/**
 * Hook to fetch a paginated list of contacts
 */
export function useContacts(filters?: ContactFilters) {
  return useQuery({
    queryKey: contactKeys.list(filters),
    queryFn: () => contactsApi.list(filters),
  });
}

/**
 * Hook to fetch a single contact by ID
 */
export function useContact(id: number | undefined) {
  return useQuery({
    queryKey: contactKeys.detail(id!),
    queryFn: () => contactsApi.get(id!),
    enabled: !!id,
  });
}

/**
 * Hook to create a new contact
 */
export function useCreateContact() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ContactCreate) => contactsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: contactKeys.lists() });
    },
  });
}

/**
 * Hook to update a contact
 */
export function useUpdateContact() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ContactUpdate }) =>
      contactsApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: contactKeys.lists() });
      queryClient.invalidateQueries({ queryKey: contactKeys.detail(id) });
    },
  });
}

/**
 * Hook to delete a contact
 */
export function useDeleteContact() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => contactsApi.delete(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: contactKeys.lists() });
      queryClient.removeQueries({ queryKey: contactKeys.detail(id) });
    },
  });
}

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

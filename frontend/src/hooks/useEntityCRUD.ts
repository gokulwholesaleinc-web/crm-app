/**
 * Generic entity CRUD hook factory using TanStack Query.
 * This provides a DRY pattern for creating entity-specific hooks.
 */

import {
  useMutation,
  useQueryClient,
  UseQueryOptions,
  QueryKey,
} from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { useAuthQuery } from './useAuthQuery';

// Generic paginated response type
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// Generic list params type
export interface ListParams {
  page?: number;
  page_size?: number;
  search?: string;
  [key: string]: string | number | boolean | undefined;
}

// Configuration for entity CRUD operations
export interface EntityConfig<T> {
  entityName: string;
  baseUrl: string;
  queryKey: string;
  // Optional transform functions
  transformResponse?: (data: unknown) => T;
  transformListResponse?: (data: unknown) => PaginatedResponse<T>;
}

/**
 * Creates a set of CRUD hooks for a given entity type.
 * @template T - The entity type
 * @template TCreate - The type for creating entities
 * @template TUpdate - The type for updating entities
 * @template TFilters - The type for filter parameters (defaults to ListParams)
 */
export function createEntityHooks<
  T extends { id: number },
  TCreate = Omit<T, 'id' | 'created_at' | 'updated_at'>,
  TUpdate = Partial<TCreate>,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  TFilters = any
>(config: EntityConfig<T>) {
  const { baseUrl, queryKey, transformResponse, transformListResponse } = config;

  /**
   * Hook to fetch a paginated list of entities
   */
  function useList(
    params?: TFilters,
    options?: Omit<UseQueryOptions<PaginatedResponse<T>>, 'queryKey' | 'queryFn'>
  ) {
    return useAuthQuery({
      queryKey: [queryKey, 'list', params] as QueryKey,
      queryFn: async () => {
        const response = await apiClient.get<PaginatedResponse<T>>(baseUrl, { params });
        return transformListResponse ? transformListResponse(response.data) : response.data;
      },
      ...options,
    });
  }

  /**
   * Hook to fetch a single entity by ID
   */
  function useOne(
    id: number | undefined,
    options?: Omit<UseQueryOptions<T>, 'queryKey' | 'queryFn'>
  ) {
    return useAuthQuery({
      queryKey: [queryKey, 'detail', id] as QueryKey,
      queryFn: async () => {
        const response = await apiClient.get<T>(`${baseUrl}/${id}`);
        return transformResponse ? transformResponse(response.data) : response.data;
      },
      enabled: !!id,
      ...options,
    });
  }

  /**
   * Hook to create a new entity
   */
  function useCreate() {
    const queryClient = useQueryClient();

    return useMutation({
      mutationFn: async (data: TCreate) => {
        const response = await apiClient.post<T>(baseUrl, data);
        return transformResponse ? transformResponse(response.data) : response.data;
      },
      onSuccess: () => {
        // Invalidate list queries
        queryClient.invalidateQueries({ queryKey: [queryKey, 'list'] });
      },
    });
  }

  /**
   * Hook to update an existing entity
   */
  function useUpdate() {
    const queryClient = useQueryClient();

    return useMutation({
      mutationFn: async ({ id, data }: { id: number; data: TUpdate }) => {
        const response = await apiClient.patch<T>(`${baseUrl}/${id}`, data);
        return transformResponse ? transformResponse(response.data) : response.data;
      },
      onSuccess: (_data, variables) => {
        // Invalidate both list and detail queries
        queryClient.invalidateQueries({ queryKey: [queryKey, 'list'] });
        queryClient.invalidateQueries({ queryKey: [queryKey, 'detail', variables.id] });
      },
    });
  }

  /**
   * Hook to delete an entity
   */
  function useDelete() {
    const queryClient = useQueryClient();

    return useMutation({
      mutationFn: async (id: number) => {
        await apiClient.delete(`${baseUrl}/${id}`);
      },
      onSuccess: (_data, variables) => {
        // Invalidate list queries and remove detail from cache
        queryClient.invalidateQueries({ queryKey: [queryKey, 'list'] });
        queryClient.removeQueries({ queryKey: [queryKey, 'detail', variables] });
      },
    });
  }

  return {
    useList,
    useOne,
    useCreate,
    useUpdate,
    useDelete,
  };
}

/**
 * Utility to create query keys for consistent cache management
 */
export function createQueryKeys(entityName: string) {
  return {
    all: [entityName] as const,
    lists: () => [entityName, 'list'] as const,
    list: (params?: ListParams) => [entityName, 'list', params] as const,
    details: () => [entityName, 'detail'] as const,
    detail: (id: number) => [entityName, 'detail', id] as const,
  };
}

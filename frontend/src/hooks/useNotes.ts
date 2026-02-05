/**
 * Notes hooks using TanStack Query for data fetching and caching.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthQuery } from './useAuthQuery';
import { notesApi } from '../api/notes';
import type {
  NoteCreate,
  NoteUpdate,
  NoteFilters,
} from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const noteKeys = {
  all: ['notes'] as const,
  lists: () => [...noteKeys.all, 'list'] as const,
  list: (filters: NoteFilters) => [...noteKeys.lists(), filters] as const,
  details: () => [...noteKeys.all, 'detail'] as const,
  detail: (id: number) => [...noteKeys.details(), id] as const,
  entity: (entityType: string, entityId: number) =>
    [...noteKeys.all, 'entity', entityType, entityId] as const,
};

// =============================================================================
// List and Detail Hooks
// =============================================================================

/**
 * Hook to fetch a paginated list of notes
 */
export function useNotes(filters?: NoteFilters) {
  return useAuthQuery({
    queryKey: noteKeys.list(filters || {}),
    queryFn: () => notesApi.list(filters),
  });
}

/**
 * Hook to fetch notes for a specific entity
 */
export function useEntityNotes(
  entityType: string,
  entityId: number,
  page = 1,
  pageSize = 50
) {
  return useAuthQuery({
    queryKey: noteKeys.entity(entityType, entityId),
    queryFn: () => notesApi.getEntityNotes(entityType, entityId, page, pageSize),
    enabled: !!entityType && !!entityId,
  });
}

/**
 * Hook to fetch a single note by ID
 */
export function useNote(id: number | undefined) {
  return useAuthQuery({
    queryKey: noteKeys.detail(id!),
    queryFn: () => notesApi.get(id!),
    enabled: !!id,
  });
}

// =============================================================================
// Mutation Hooks
// =============================================================================

/**
 * Hook to create a new note
 */
export function useCreateNote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: NoteCreate) => notesApi.create(data),
    onSuccess: (newNote) => {
      // Invalidate all note lists
      queryClient.invalidateQueries({ queryKey: noteKeys.lists() });
      // Invalidate entity-specific notes
      queryClient.invalidateQueries({
        queryKey: noteKeys.entity(newNote.entity_type, newNote.entity_id),
      });
    },
  });
}

/**
 * Hook to update a note
 */
export function useUpdateNote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: NoteUpdate }) =>
      notesApi.update(id, data),
    onSuccess: (updatedNote, { id }) => {
      // Invalidate all note lists
      queryClient.invalidateQueries({ queryKey: noteKeys.lists() });
      // Invalidate specific note detail
      queryClient.invalidateQueries({ queryKey: noteKeys.detail(id) });
      // Invalidate entity-specific notes
      queryClient.invalidateQueries({
        queryKey: noteKeys.entity(updatedNote.entity_type, updatedNote.entity_id),
      });
    },
  });
}

/**
 * Hook to delete a note
 */
export function useDeleteNote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id }: { id: number; entityType: string; entityId: number }) =>
      notesApi.delete(id),
    onSuccess: (_, variables) => {
      const { id, entityType, entityId } = variables;
      // Invalidate all note lists
      queryClient.invalidateQueries({ queryKey: noteKeys.lists() });
      // Invalidate specific note detail
      queryClient.invalidateQueries({ queryKey: noteKeys.detail(id) });
      // Invalidate entity-specific notes
      queryClient.invalidateQueries({
        queryKey: noteKeys.entity(entityType, entityId),
      });
    },
  });
}

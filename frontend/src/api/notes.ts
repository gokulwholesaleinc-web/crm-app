/**
 * Notes API
 */

import { apiClient } from './client';
import type {
  Note,
  NoteCreate,
  NoteUpdate,
  NoteListResponse,
  NoteFilters,
} from '../types';

const NOTES_BASE = '/api/notes';

// =============================================================================
// Notes CRUD
// =============================================================================

/**
 * List notes with pagination and filters
 */
export const listNotes = async (
  filters: NoteFilters = {}
): Promise<NoteListResponse> => {
  const response = await apiClient.get<NoteListResponse>(NOTES_BASE, {
    params: filters,
  });
  return response.data;
};

/**
 * Get a note by ID
 */
export const getNote = async (noteId: number): Promise<Note> => {
  const response = await apiClient.get<Note>(`${NOTES_BASE}/${noteId}`);
  return response.data;
};

/**
 * Create a new note
 */
export const createNote = async (noteData: NoteCreate): Promise<Note> => {
  const response = await apiClient.post<Note>(NOTES_BASE, noteData);
  return response.data;
};

/**
 * Update a note
 */
export const updateNote = async (
  noteId: number,
  noteData: NoteUpdate
): Promise<Note> => {
  const response = await apiClient.patch<Note>(
    `${NOTES_BASE}/${noteId}`,
    noteData
  );
  return response.data;
};

/**
 * Delete a note
 */
export const deleteNote = async (noteId: number): Promise<void> => {
  await apiClient.delete(`${NOTES_BASE}/${noteId}`);
};

// =============================================================================
// Entity-specific helpers
// =============================================================================

/**
 * Get notes for a specific entity
 */
export const getEntityNotes = async (
  entityType: string,
  entityId: number,
  page = 1,
  pageSize = 50
): Promise<NoteListResponse> => {
  return listNotes({
    entity_type: entityType,
    entity_id: entityId,
    page,
    page_size: pageSize,
  });
};

// Export all note functions
export const notesApi = {
  // CRUD
  list: listNotes,
  get: getNote,
  create: createNote,
  update: updateNote,
  delete: deleteNote,
  // Entity-specific
  getEntityNotes,
};

export default notesApi;

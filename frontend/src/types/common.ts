/**
 * Common / Shared Types
 */

/**
 * Generic paginated list response
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

/**
 * Generic API error response
 */
export interface ApiError {
  detail: string;
  status_code?: number;
}

export interface TagBrief {
  id: number;
  name: string;
  color?: string | null;
}

export interface CompanyBrief {
  id: number;
  name: string;
}

export interface ContactBrief {
  id: number;
  full_name: string;
}

export interface Note {
  id: number;
  content: string;
  entity_type: string;
  entity_id: number;
  created_at: string;
  updated_at: string;
  created_by_id: number | null;
  author_name?: string | null;
}

export interface NoteCreate {
  content: string;
  entity_type: string;
  entity_id: number;
}

export interface NoteUpdate {
  content?: string | null;
}

export type NoteListResponse = PaginatedResponse<Note>;

export interface NoteFilters {
  page?: number;
  page_size?: number;
  entity_type?: string;
  entity_id?: number;
}

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
  /** Flattened, display-ready detail string. Always set so toasts can
   *  consume it directly without typeguards. */
  detail: string;
  /** Original `detail` payload from the backend response, preserved
   *  unmodified so callers that need to inspect structured errors
   *  (e.g. `{pending_approval: true}` from the Google OAuth callback,
   *  or FastAPI's array of validation issues) can read the shape
   *  instead of having to re-parse the flattened JSON string. */
  rawDetail?: unknown;
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

/**
 * Variant used by authenticated entity-detail surfaces that drive
 * Send-button gating client-side. Never use for public-token responses;
 * see backend `core.schemas.ContactBriefWithEmail`.
 */
export interface ContactBriefWithEmail extends ContactBrief {
  email?: string | null;
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

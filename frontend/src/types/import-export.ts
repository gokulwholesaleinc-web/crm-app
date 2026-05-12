// Import/Export Types

export interface DuplicateEntry {
  row: number;
  email: string;
  label: string;
}

export type ImportMatchKey = 'none' | 'email' | 'phone' | 'name_plus_company';
export type ImportMergeStrategy = 'preserve_existing' | 'overwrite_all';

export interface ImportFieldChange {
  field: string;
  old: unknown;
  new: unknown;
}

export interface ImportUpdateRow {
  row: number;
  existing_id: number;
  match_key: ImportMatchKey;
  match_value: string;
  merge_strategy: ImportMergeStrategy;
  field_changes: ImportFieldChange[];
  noop: boolean;
}

export interface ImportConflictRow {
  row: number;
  match_key: ImportMatchKey;
  match_value: string;
  existing_ids: number[];
  reason: string;
}

export interface ImportResult {
  success: boolean;
  imported_count: number;
  errors: string[];
  duplicates_skipped: number;
  duplicates: DuplicateEntry[];
  contacts_created?: number;
  contacts_linked?: number;
  updated_count?: number;
  updates?: ImportUpdateRow[];
  conflicts?: ImportConflictRow[];
  dry_run?: boolean;
}

export interface ContactMatchCandidate {
  contact_id: number;
  name: string;
  email: string | null;
  match_pct: number;
}

export interface ContactMatch {
  row: number;
  csv_name: string;
  first_name: string;
  last_name: string;
  candidates: ContactMatchCandidate[];
}

export interface ContactDecision {
  csv_name: string;
  action: 'create_new' | 'link_existing' | 'skip';
  contact_id?: number;
}

export interface ImportPreview {
  total_rows: number;
  csv_headers: string[];
  available_fields: string[];
  column_mapping: Record<string, string>;
  unmapped_columns: string[];
  missing_fields: string[];
  preview_rows: Record<string, string>[];
  warnings: string[];
  source_detected?: string | null;
  is_linkedin_format?: boolean;
  contact_person_column?: string;
  contact_matches?: ContactMatch[];
}

export type ImportExportEntityType = 'contacts' | 'companies' | 'leads';

// Bulk Operation Types

export interface BulkUpdateRequest {
  entity_type: string;
  entity_ids: number[];
  updates: Record<string, unknown>;
}

export interface BulkAssignRequest {
  entity_type: string;
  entity_ids: number[];
  owner_id: number;
}

export interface BulkOperationResult {
  success: boolean;
  updated: number;
  entity_type: string;
  error?: string;
  updates_applied?: Record<string, unknown>;
  owner_id?: number;
}

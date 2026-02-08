/**
 * Saved Filters API client
 */
import { apiClient } from './client';

export interface FilterCondition {
  field: string;
  op: string;
  value?: unknown;
}

export interface FilterGroup {
  operator: 'and' | 'or';
  conditions: (FilterCondition | FilterGroup)[];
}

export interface SavedFilter {
  id: number;
  name: string;
  entity_type: string;
  filters: FilterGroup;
  user_id: number;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface SavedFilterCreate {
  name: string;
  entity_type: string;
  filters: FilterGroup;
  is_default?: boolean;
}

export const listSavedFilters = async (entityType?: string): Promise<SavedFilter[]> => {
  const params: Record<string, string> = {};
  if (entityType) params.entity_type = entityType;
  const { data } = await apiClient.get('/api/filters', { params });
  return data;
};

export const createSavedFilter = async (filter: SavedFilterCreate): Promise<SavedFilter> => {
  const { data } = await apiClient.post('/api/filters', filter);
  return data;
};

export const deleteSavedFilter = async (id: number): Promise<void> => {
  await apiClient.delete(`/api/filters/${id}`);
};

export const filtersApi = {
  listSavedFilters,
  createSavedFilter,
  deleteSavedFilter,
};

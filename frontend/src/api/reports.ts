/**
 * Reports API client
 */
import { apiClient } from './client';

// Types
export interface ReportDefinition {
  entity_type: string;
  metric: string;
  metric_field?: string | null;
  group_by?: string | null;
  date_group?: string | null;
  filters?: Record<string, unknown> | null;
  chart_type: string;
}

export interface ReportDataPoint {
  label: string;
  value: number;
}

export interface ReportResult {
  entity_type: string;
  metric: string;
  metric_field?: string | null;
  group_by?: string | null;
  chart_type: string;
  data: ReportDataPoint[];
  total?: number | null;
}

export interface SavedReport {
  id: number;
  name: string;
  description?: string | null;
  entity_type: string;
  filters?: Record<string, unknown> | null;
  group_by?: string | null;
  date_group?: string | null;
  metric: string;
  metric_field?: string | null;
  chart_type: string;
  created_by_id: number;
  is_public: boolean;
  created_at: string;
  updated_at: string;
}

export interface SavedReportCreate {
  name: string;
  description?: string | null;
  entity_type: string;
  filters?: Record<string, unknown> | null;
  group_by?: string | null;
  date_group?: string | null;
  metric?: string;
  metric_field?: string | null;
  chart_type?: string;
  is_public?: boolean;
}

export interface ReportTemplate {
  id: string;
  name: string;
  description: string;
  entity_type: string;
  metric: string;
  metric_field?: string | null;
  group_by?: string | null;
  date_group?: string | null;
  chart_type: string;
  filters?: Record<string, unknown> | null;
}

// API functions
export const executeReport = async (definition: ReportDefinition): Promise<ReportResult> => {
  const { data } = await apiClient.post('/api/reports/execute', definition);
  return data;
};

export const exportReportCsv = async (definition: ReportDefinition): Promise<Blob> => {
  const { data } = await apiClient.post('/api/reports/export-csv', definition, {
    responseType: 'blob',
  });
  return data;
};

export const listReportTemplates = async (): Promise<ReportTemplate[]> => {
  const { data } = await apiClient.get('/api/reports/templates');
  return data;
};

export const listSavedReports = async (entityType?: string): Promise<SavedReport[]> => {
  const params: Record<string, string> = {};
  if (entityType) params.entity_type = entityType;
  const { data } = await apiClient.get('/api/reports', { params });
  return data;
};

export const createSavedReport = async (report: SavedReportCreate): Promise<SavedReport> => {
  const { data } = await apiClient.post('/api/reports', report);
  return data;
};

export const getSavedReport = async (id: number): Promise<SavedReport> => {
  const { data } = await apiClient.get(`/api/reports/${id}`);
  return data;
};

export const deleteSavedReport = async (id: number): Promise<void> => {
  await apiClient.delete(`/api/reports/${id}`);
};

export const reportsApi = {
  executeReport,
  exportReportCsv,
  listReportTemplates,
  listSavedReports,
  createSavedReport,
  getSavedReport,
  deleteSavedReport,
};

/**
 * Import/Export API
 * Handles CSV import and export operations for contacts, companies, and leads.
 */

import { apiClient } from './client';
import type { ImportResult, ImportExportEntityType, BulkUpdateRequest, BulkAssignRequest, BulkOperationResult } from '../types';

const IMPORT_EXPORT_BASE = '/api/import-export';

/**
 * Export contacts as CSV
 */
export const exportContacts = async (): Promise<Blob> => {
  const response = await apiClient.get(`${IMPORT_EXPORT_BASE}/export/contacts`, {
    responseType: 'blob',
  });
  return response.data;
};

/**
 * Export companies as CSV
 */
export const exportCompanies = async (): Promise<Blob> => {
  const response = await apiClient.get(`${IMPORT_EXPORT_BASE}/export/companies`, {
    responseType: 'blob',
  });
  return response.data;
};

/**
 * Export leads as CSV
 */
export const exportLeads = async (): Promise<Blob> => {
  const response = await apiClient.get(`${IMPORT_EXPORT_BASE}/export/leads`, {
    responseType: 'blob',
  });
  return response.data;
};

/**
 * Import contacts from CSV file
 */
export const importContacts = async (
  file: File,
  skipErrors: boolean = true
): Promise<ImportResult> => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiClient.post<ImportResult>(
    `${IMPORT_EXPORT_BASE}/import/contacts`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      params: { skip_errors: skipErrors },
    }
  );
  return response.data;
};

/**
 * Import companies from CSV file
 */
export const importCompanies = async (
  file: File,
  skipErrors: boolean = true
): Promise<ImportResult> => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiClient.post<ImportResult>(
    `${IMPORT_EXPORT_BASE}/import/companies`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      params: { skip_errors: skipErrors },
    }
  );
  return response.data;
};

/**
 * Import leads from CSV file
 */
export const importLeads = async (
  file: File,
  skipErrors: boolean = true
): Promise<ImportResult> => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiClient.post<ImportResult>(
    `${IMPORT_EXPORT_BASE}/import/leads`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      params: { skip_errors: skipErrors },
    }
  );
  return response.data;
};

/**
 * Get CSV template for importing an entity type
 */
export const getTemplate = async (entityType: ImportExportEntityType): Promise<Blob> => {
  const response = await apiClient.get(
    `${IMPORT_EXPORT_BASE}/template/${entityType}`,
    {
      responseType: 'blob',
    }
  );
  return response.data;
};

/**
 * Helper function to download a blob as a file
 */
export const downloadBlob = (blob: Blob, filename: string): void => {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

/**
 * Helper function to generate export filename with date
 */
export const generateExportFilename = (entityType: string): string => {
  const date = new Date().toISOString().split('T')[0];
  return `${entityType}_export_${date}.csv`;
};

// =============================================================================
// Bulk Operations
// =============================================================================

export const bulkUpdate = async (data: BulkUpdateRequest): Promise<BulkOperationResult> => {
  const response = await apiClient.post<BulkOperationResult>(
    `${IMPORT_EXPORT_BASE}/bulk/update`,
    data
  );
  return response.data;
};

export const bulkAssign = async (data: BulkAssignRequest): Promise<BulkOperationResult> => {
  const response = await apiClient.post<BulkOperationResult>(
    `${IMPORT_EXPORT_BASE}/bulk/assign`,
    data
  );
  return response.data;
};

// Export all import/export functions
export const importExportApi = {
  exportContacts,
  exportCompanies,
  exportLeads,
  importContacts,
  importCompanies,
  importLeads,
  getTemplate,
  downloadBlob,
  generateExportFilename,
  bulkUpdate,
  bulkAssign,
};

export default importExportApi;

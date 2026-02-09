/**
 * Reports hooks using TanStack Query.
 * Provides hooks for report execution, templates, and saved reports.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { reportsApi } from '../api/reports';
import type {
  ReportDefinition,
  SavedReportCreate,
} from '../api/reports';
import { useAuthQuery } from './useAuthQuery';

// =============================================================================
// Query Keys
// =============================================================================

export const reportKeys = {
  all: ['reports'] as const,
  templates: () => ['reports', 'templates'] as const,
  lists: () => ['reports', 'list'] as const,
  list: (entityType?: string) => ['reports', 'list', entityType] as const,
  details: () => ['reports', 'detail'] as const,
  detail: (id: number) => ['reports', 'detail', id] as const,
  execution: (definition: ReportDefinition) => ['reports', 'execution', definition] as const,
};

// =============================================================================
// Query Hooks
// =============================================================================

export function useReportTemplates() {
  return useAuthQuery({
    queryKey: reportKeys.templates(),
    queryFn: () => reportsApi.listReportTemplates(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useSavedReports(entityType?: string) {
  return useAuthQuery({
    queryKey: reportKeys.list(entityType),
    queryFn: () => reportsApi.listSavedReports(entityType),
  });
}

export function useSavedReport(id: number | undefined) {
  return useAuthQuery({
    queryKey: reportKeys.detail(id!),
    queryFn: () => reportsApi.getSavedReport(id!),
    enabled: !!id,
  });
}

// =============================================================================
// Mutation Hooks
// =============================================================================

export function useExecuteReport() {
  return useMutation({
    mutationFn: (definition: ReportDefinition) => reportsApi.executeReport(definition),
  });
}

export function useExportReportCsv() {
  return useMutation({
    mutationFn: (definition: ReportDefinition) => reportsApi.exportReportCsv(definition),
  });
}

export function useCreateSavedReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: SavedReportCreate) => reportsApi.createSavedReport(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: reportKeys.lists() });
    },
  });
}

export function useDeleteSavedReport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => reportsApi.deleteSavedReport(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: reportKeys.lists() });
      queryClient.removeQueries({ queryKey: reportKeys.detail(id) });
    },
  });
}

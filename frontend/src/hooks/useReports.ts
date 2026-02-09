/**
 * Report hooks using TanStack Query.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthQuery } from './useAuthQuery';
import {
  executeReport,
  exportReportCsv,
  listReportTemplates,
  listSavedReports,
  createSavedReport,
  getSavedReport,
  deleteSavedReport,
} from '../api/reports';
import type { ReportDefinition, SavedReportCreate } from '../api/reports';

export const reportKeys = {
  all: ['reports'] as const,
  templates: () => [...reportKeys.all, 'templates'] as const,
  saved: () => [...reportKeys.all, 'saved'] as const,
  savedByEntity: (entityType: string) => [...reportKeys.saved(), entityType] as const,
  savedById: (id: number) => [...reportKeys.saved(), id] as const,
};

export const useReportTemplates = () =>
  useAuthQuery({
    queryKey: reportKeys.templates(),
    queryFn: listReportTemplates,
    staleTime: 1000 * 60 * 30,
  });

export const useSavedReports = (entityType?: string) =>
  useAuthQuery({
    queryKey: entityType ? reportKeys.savedByEntity(entityType) : reportKeys.saved(),
    queryFn: () => listSavedReports(entityType),
  });

export const useSavedReport = (id: number) =>
  useAuthQuery({
    queryKey: reportKeys.savedById(id),
    queryFn: () => getSavedReport(id),
    enabled: id > 0,
  });

export const useExecuteReport = () =>
  useMutation({
    mutationFn: (definition: ReportDefinition) => executeReport(definition),
  });

export const useExportReportCsv = () =>
  useMutation({
    mutationFn: (definition: ReportDefinition) => exportReportCsv(definition),
  });

export const useCreateSavedReport = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SavedReportCreate) => createSavedReport(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: reportKeys.saved() });
    },
  });
};

export const useDeleteSavedReport = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteSavedReport(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: reportKeys.saved() });
    },
  });
};

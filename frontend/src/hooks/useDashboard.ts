/**
 * Dashboard hooks using TanStack Query
 */

import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '../api/dashboard';
import type { DateRangeParams } from '../api/dashboard';
import { useAuthStore } from '../store/authStore';
import { CACHE_TIMES } from '../config/queryConfig';
import type { ChartData } from '../types';

// Query keys
export const dashboardKeys = {
  all: ['dashboard'] as const,
  full: (dateRange?: DateRangeParams) => [...dashboardKeys.all, 'full', dateRange?.dateFrom, dateRange?.dateTo] as const,
  kpis: (dateRange?: DateRangeParams) => [...dashboardKeys.all, 'kpis', dateRange?.dateFrom, dateRange?.dateTo] as const,
  charts: () => [...dashboardKeys.all, 'charts'] as const,
  chart: (chartType: string, params?: Record<string, unknown>) =>
    [...dashboardKeys.charts(), chartType, params] as const,
};

/**
 * Hook to fetch the full dashboard data (KPIs + charts)
 */
export function useDashboard(dateRange?: DateRangeParams) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.full(dateRange),
    queryFn: () => dashboardApi.getDashboard(dateRange),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch only KPIs
 */
export function useKPIs(dateRange?: DateRangeParams) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.kpis(dateRange),
    queryFn: () => dashboardApi.getKpis(dateRange),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch pipeline funnel chart
 */
export function usePipelineFunnelChart(dateRange?: DateRangeParams) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('pipeline-funnel', { dateFrom: dateRange?.dateFrom, dateTo: dateRange?.dateTo }),
    queryFn: () => dashboardApi.getPipelineFunnelChart(dateRange),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch leads by status chart
 */
export function useLeadsByStatusChart(dateRange?: DateRangeParams) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('leads-by-status', { dateFrom: dateRange?.dateFrom, dateTo: dateRange?.dateTo }),
    queryFn: () => dashboardApi.getLeadsByStatusChart(dateRange),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch leads by source chart
 */
export function useLeadsBySourceChart(dateRange?: DateRangeParams) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('leads-by-source', { dateFrom: dateRange?.dateFrom, dateTo: dateRange?.dateTo }),
    queryFn: () => dashboardApi.getLeadsBySourceChart(dateRange),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch revenue trend chart
 */
export function useRevenueTrendChart(months = 6, dateRange?: DateRangeParams) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('revenue-trend', { months, dateFrom: dateRange?.dateFrom, dateTo: dateRange?.dateTo }),
    queryFn: () => dashboardApi.getRevenueTrendChart(months, dateRange),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch activities by type chart
 */
export function useActivitiesChart(days = 30, dateRange?: DateRangeParams) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('activities', { days, dateFrom: dateRange?.dateFrom, dateTo: dateRange?.dateTo }),
    queryFn: () => dashboardApi.getActivitiesChart(days, dateRange),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch new leads trend chart
 */
export function useNewLeadsTrendChart(weeks = 8, dateRange?: DateRangeParams) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('new-leads-trend', { weeks, dateFrom: dateRange?.dateFrom, dateTo: dateRange?.dateTo }),
    queryFn: () => dashboardApi.getNewLeadsTrendChart(weeks, dateRange),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch conversion rates chart
 */
export function useConversionRatesChart(dateRange?: DateRangeParams) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('conversion-rates', { dateFrom: dateRange?.dateFrom, dateTo: dateRange?.dateTo }),
    queryFn: () => dashboardApi.getConversionRatesChart(dateRange),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch sales funnel data
 */
export function useSalesFunnel(dateRange?: DateRangeParams) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('sales-funnel', { dateFrom: dateRange?.dateFrom, dateTo: dateRange?.dateTo }),
    queryFn: () => dashboardApi.getSalesFunnel(dateRange),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch sales pipeline KPIs
 */
export function useSalesKpis(dateRange?: DateRangeParams) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('sales-kpis', { dateFrom: dateRange?.dateFrom, dateTo: dateRange?.dateTo }),
    queryFn: () => dashboardApi.getSalesKpis(dateRange),
    ...CACHE_TIMES.DASHBOARD,
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Combined hook to get all chart data
 */
export function useCharts(dateRange?: DateRangeParams) {
  const pipelineFunnel = usePipelineFunnelChart(dateRange);
  const leadsByStatus = useLeadsByStatusChart(dateRange);
  const leadsBySource = useLeadsBySourceChart(dateRange);
  const revenueTrend = useRevenueTrendChart(6, dateRange);
  const activities = useActivitiesChart(30, dateRange);
  const newLeadsTrend = useNewLeadsTrendChart(8, dateRange);

  const isLoading =
    pipelineFunnel.isLoading ||
    leadsByStatus.isLoading ||
    leadsBySource.isLoading ||
    revenueTrend.isLoading ||
    activities.isLoading ||
    newLeadsTrend.isLoading;

  const isError =
    pipelineFunnel.isError ||
    leadsByStatus.isError ||
    leadsBySource.isError ||
    revenueTrend.isError ||
    activities.isError ||
    newLeadsTrend.isError;

  const charts: ChartData[] = [
    pipelineFunnel.data,
    leadsByStatus.data,
    leadsBySource.data,
    revenueTrend.data,
    activities.data,
    newLeadsTrend.data,
  ].filter((chart): chart is ChartData => !!chart);

  return {
    charts,
    isLoading,
    isError,
    pipelineFunnel,
    leadsByStatus,
    leadsBySource,
    revenueTrend,
    activities,
    newLeadsTrend,
  };
}

/**
 * Dashboard hooks using TanStack Query
 */

import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '../api/dashboard';
import { useAuthStore } from '../store/authStore';
import type { ChartData } from '../types';

// Query keys
export const dashboardKeys = {
  all: ['dashboard'] as const,
  full: () => [...dashboardKeys.all, 'full'] as const,
  kpis: () => [...dashboardKeys.all, 'kpis'] as const,
  charts: () => [...dashboardKeys.all, 'charts'] as const,
  chart: (chartType: string, params?: Record<string, unknown>) =>
    [...dashboardKeys.charts(), chartType, params] as const,
};

/**
 * Hook to fetch the full dashboard data (KPIs + charts)
 */
export function useDashboard() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.full(),
    queryFn: () => dashboardApi.getDashboard(),
    staleTime: 60 * 1000, // 1 minute - dashboard data should refresh periodically
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch only KPIs
 */
export function useKPIs() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.kpis(),
    queryFn: () => dashboardApi.getKpis(),
    staleTime: 60 * 1000,
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch pipeline funnel chart
 */
export function usePipelineFunnelChart() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('pipeline-funnel'),
    queryFn: () => dashboardApi.getPipelineFunnelChart(),
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch leads by status chart
 */
export function useLeadsByStatusChart() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('leads-by-status'),
    queryFn: () => dashboardApi.getLeadsByStatusChart(),
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch leads by source chart
 */
export function useLeadsBySourceChart() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('leads-by-source'),
    queryFn: () => dashboardApi.getLeadsBySourceChart(),
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch revenue trend chart
 */
export function useRevenueTrendChart(months = 6) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('revenue-trend', { months }),
    queryFn: () => dashboardApi.getRevenueTrendChart(months),
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch activities by type chart
 */
export function useActivitiesChart(days = 30) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('activities', { days }),
    queryFn: () => dashboardApi.getActivitiesChart(days),
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch new leads trend chart
 */
export function useNewLeadsTrendChart(weeks = 8) {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('new-leads-trend', { weeks }),
    queryFn: () => dashboardApi.getNewLeadsTrendChart(weeks),
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch conversion rates chart
 */
export function useConversionRatesChart() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('conversion-rates'),
    queryFn: () => dashboardApi.getConversionRatesChart(),
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch sales funnel data
 */
export function useSalesFunnel() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('sales-funnel'),
    queryFn: () => dashboardApi.getSalesFunnel(),
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Hook to fetch sales pipeline KPIs
 */
export function useSalesKpis() {
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  return useQuery({
    queryKey: dashboardKeys.chart('sales-kpis'),
    queryFn: () => dashboardApi.getSalesKpis(),
    staleTime: 60 * 1000,
    enabled: isAuthenticated && !authLoading,
  });
}

/**
 * Combined hook to get all chart data
 */
export function useCharts() {
  const pipelineFunnel = usePipelineFunnelChart();
  const leadsByStatus = useLeadsByStatusChart();
  const leadsBySource = useLeadsBySourceChart();
  const revenueTrend = useRevenueTrendChart();
  const activities = useActivitiesChart();
  const newLeadsTrend = useNewLeadsTrendChart();

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

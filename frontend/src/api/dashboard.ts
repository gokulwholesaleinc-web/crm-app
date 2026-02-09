/**
 * Dashboard API
 */

import { apiClient } from './client';
import type {
  DashboardResponse,
  NumberCardData,
  ChartData,
  SalesFunnelResponse,
} from '../types';

const DASHBOARD_BASE = '/api/dashboard';

// =============================================================================
// Dashboard
// =============================================================================

/**
 * Get full dashboard data including KPIs and charts
 */
export const getDashboard = async (): Promise<DashboardResponse> => {
  const response = await apiClient.get<DashboardResponse>(DASHBOARD_BASE);
  return response.data;
};

/**
 * Get KPI number cards only
 */
export const getKpis = async (): Promise<NumberCardData[]> => {
  const response = await apiClient.get<NumberCardData[]>(`${DASHBOARD_BASE}/kpis`);
  return response.data;
};

// =============================================================================
// Charts
// =============================================================================

/**
 * Get pipeline funnel chart data
 */
export const getPipelineFunnelChart = async (): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/pipeline-funnel`
  );
  return response.data;
};

/**
 * Get leads by status chart data
 */
export const getLeadsByStatusChart = async (): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/leads-by-status`
  );
  return response.data;
};

/**
 * Get leads by source chart data
 */
export const getLeadsBySourceChart = async (): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/leads-by-source`
  );
  return response.data;
};

/**
 * Get monthly revenue trend chart data
 */
export const getRevenueTrendChart = async (months = 6): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/revenue-trend`,
    { params: { months } }
  );
  return response.data;
};

/**
 * Get activities by type chart data
 */
export const getActivitiesChart = async (days = 30): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/activities`,
    { params: { days } }
  );
  return response.data;
};

/**
 * Get new leads trend chart data
 */
export const getNewLeadsTrendChart = async (weeks = 8): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/new-leads-trend`,
    { params: { weeks } }
  );
  return response.data;
};

/**
 * Get conversion rates chart data
 */
export const getConversionRatesChart = async (): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/conversion-rates`
  );
  return response.data;
};

/**
 * Get sales funnel data
 */
export const getSalesFunnel = async (): Promise<SalesFunnelResponse> => {
  const response = await apiClient.get<SalesFunnelResponse>(`${DASHBOARD_BASE}/funnel`);
  return response.data;
};

// =============================================================================
// Multi-Currency
// =============================================================================

export interface CurrencyInfo {
  code: string;
  name: string;
  symbol: string;
  exchange_rate: number;
}

export interface CurrenciesResponse {
  base_currency: string;
  currencies: CurrencyInfo[];
}

export interface ConvertedRevenueResponse {
  target_currency: string;
  total_pipeline_value: number;
  total_revenue: number;
  weighted_pipeline_value: number;
  open_deal_count: number;
  won_deal_count: number;
}

/**
 * Get list of supported currencies with exchange rates
 */
export const getCurrencies = async (): Promise<CurrenciesResponse> => {
  const response = await apiClient.get<CurrenciesResponse>(`${DASHBOARD_BASE}/currencies`);
  return response.data;
};

/**
 * Get revenue converted to target currency
 */
export const getConvertedRevenue = async (
  targetCurrency = 'USD'
): Promise<ConvertedRevenueResponse> => {
  const response = await apiClient.get<ConvertedRevenueResponse>(
    `${DASHBOARD_BASE}/revenue/converted`,
    { params: { target_currency: targetCurrency } }
  );
  return response.data;
};

// Export all dashboard functions
export const dashboardApi = {
  // Main
  getDashboard,
  getKpis,
  // Charts
  getPipelineFunnelChart,
  getLeadsByStatusChart,
  getLeadsBySourceChart,
  getRevenueTrendChart,
  getActivitiesChart,
  getNewLeadsTrendChart,
  getConversionRatesChart,
  getSalesFunnel,
  // Multi-Currency
  getCurrencies,
  getConvertedRevenue,
};

export default dashboardApi;

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

// Dashboard

export interface DateRangeParams {
  dateFrom?: string | null;
  dateTo?: string | null;
}

function buildDateParams(dateRange?: DateRangeParams): Record<string, string> {
  const params: Record<string, string> = {};
  if (dateRange?.dateFrom) params.date_from = dateRange.dateFrom;
  if (dateRange?.dateTo) params.date_to = dateRange.dateTo;
  return params;
}

/**
 * Get full dashboard data including KPIs and charts
 */
export const getDashboard = async (dateRange?: DateRangeParams): Promise<DashboardResponse> => {
  const response = await apiClient.get<DashboardResponse>(DASHBOARD_BASE, {
    params: buildDateParams(dateRange),
  });
  return response.data;
};

/**
 * Get KPI number cards only
 */
export const getKpis = async (dateRange?: DateRangeParams): Promise<NumberCardData[]> => {
  const response = await apiClient.get<NumberCardData[]>(`${DASHBOARD_BASE}/kpis`, {
    params: buildDateParams(dateRange),
  });
  return response.data;
};

// Charts

/**
 * Get pipeline funnel chart data
 */
export const getPipelineFunnelChart = async (dateRange?: DateRangeParams): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/pipeline-funnel`,
    { params: buildDateParams(dateRange) }
  );
  return response.data;
};

/**
 * Get leads by status chart data
 */
export const getLeadsByStatusChart = async (dateRange?: DateRangeParams): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/leads-by-status`,
    { params: buildDateParams(dateRange) }
  );
  return response.data;
};

/**
 * Get leads by source chart data
 */
export const getLeadsBySourceChart = async (dateRange?: DateRangeParams): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/leads-by-source`,
    { params: buildDateParams(dateRange) }
  );
  return response.data;
};

/**
 * Get monthly revenue trend chart data
 */
export const getRevenueTrendChart = async (months = 6, dateRange?: DateRangeParams): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/revenue-trend`,
    { params: { months, ...buildDateParams(dateRange) } }
  );
  return response.data;
};

/**
 * Get activities by type chart data
 */
export const getActivitiesChart = async (days = 30, dateRange?: DateRangeParams): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/activities`,
    { params: { days, ...buildDateParams(dateRange) } }
  );
  return response.data;
};

/**
 * Get new leads trend chart data
 */
export const getNewLeadsTrendChart = async (weeks = 8, dateRange?: DateRangeParams): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/new-leads-trend`,
    { params: { weeks, ...buildDateParams(dateRange) } }
  );
  return response.data;
};

/**
 * Get conversion rates chart data
 */
export const getConversionRatesChart = async (dateRange?: DateRangeParams): Promise<ChartData> => {
  const response = await apiClient.get<ChartData>(
    `${DASHBOARD_BASE}/charts/conversion-rates`,
    { params: buildDateParams(dateRange) }
  );
  return response.data;
};

/**
 * Get sales funnel data
 */
export const getSalesFunnel = async (dateRange?: DateRangeParams): Promise<SalesFunnelResponse> => {
  const response = await apiClient.get<SalesFunnelResponse>(`${DASHBOARD_BASE}/funnel`, {
    params: buildDateParams(dateRange),
  });
  return response.data;
};

// Sales KPIs

export interface SalesKPIResponse {
  quotes_sent: number;
  proposals_sent: number;
  payments_collected_total: number;
  payments_collected_count: number;
  quote_to_payment_conversion_rate: number;
}

export const getSalesKpis = async (dateRange?: DateRangeParams): Promise<SalesKPIResponse> => {
  const response = await apiClient.get<SalesKPIResponse>(`${DASHBOARD_BASE}/sales-kpis`, {
    params: buildDateParams(dateRange),
  });
  return response.data;
};

// Multi-Currency

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

// Report Widgets

export interface ReportWidget {
  id: number;
  user_id: number;
  report_id: number;
  report_name: string;
  report_chart_type: string;
  position: number;
  width: 'half' | 'full';
  is_visible: boolean;
  created_at: string;
}

export interface CreateWidgetPayload {
  report_id: number;
  position?: number;
  width?: string;
}

export interface UpdateWidgetPayload {
  position?: number;
  width?: string;
  is_visible?: boolean;
}

export interface WidgetDataResponse {
  widget_id: number;
  report_name: string;
  chart_type: string;
  result: {
    entity_type: string;
    metric: string;
    metric_field?: string | null;
    group_by?: string | null;
    chart_type: string;
    data: { label: string; value: number }[];
    total?: number | null;
  };
}

export const listDashboardWidgets = async (): Promise<ReportWidget[]> => {
  const response = await apiClient.get<ReportWidget[]>(`${DASHBOARD_BASE}/widgets`);
  return response.data;
};

export const createDashboardWidget = async (data: CreateWidgetPayload): Promise<ReportWidget> => {
  const response = await apiClient.post<ReportWidget>(`${DASHBOARD_BASE}/widgets`, data);
  return response.data;
};

export const updateDashboardWidget = async (
  id: number,
  data: UpdateWidgetPayload
): Promise<ReportWidget> => {
  const response = await apiClient.patch<ReportWidget>(`${DASHBOARD_BASE}/widgets/${id}`, data);
  return response.data;
};

export const deleteDashboardWidget = async (id: number): Promise<void> => {
  await apiClient.delete(`${DASHBOARD_BASE}/widgets/${id}`);
};

export const getDashboardWidgetData = async (id: number): Promise<WidgetDataResponse> => {
  const response = await apiClient.get<WidgetDataResponse>(`${DASHBOARD_BASE}/widgets/${id}/data`);
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
  // Sales KPIs
  getSalesKpis,
  // Multi-Currency
  getCurrencies,
  getConvertedRevenue,
  // Report Widgets
  listDashboardWidgets,
  createDashboardWidget,
  updateDashboardWidget,
  deleteDashboardWidget,
  getDashboardWidgetData,
};

export default dashboardApi;

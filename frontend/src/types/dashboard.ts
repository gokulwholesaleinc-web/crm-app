/**
 * Dashboard Types
 */

export interface NumberCardData {
  id: string;
  label: string;
  value: number | string;
  format?: string | null;
  icon?: string | null;
  color: string;
  change?: number | null;
}

export interface ChartDataPoint {
  label: string;
  value: number | string;
  color?: string | null;
}

export interface ChartData {
  type: 'bar' | 'line' | 'pie' | 'funnel' | 'area';
  title: string;
  data: ChartDataPoint[];
}

export interface DashboardResponse {
  number_cards: NumberCardData[];
  charts: ChartData[];
}

export interface NumberCardConfig {
  id: number;
  name: string;
  label: string;
  description?: string | null;
  config: string;
  color: string;
  icon?: string | null;
  is_active: boolean;
  order: number;
  show_percentage_change: boolean;
}

export interface ChartConfig {
  id: number;
  name: string;
  label: string;
  description?: string | null;
  chart_type: string;
  config: string;
  is_active: boolean;
  order: number;
  width: 'half' | 'full';
}

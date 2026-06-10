/**
 * Marketing Analytics API client. Mirrors backend/src/marketing/schemas.py.
 *
 * Money/ratio fields arrive as JSON numbers OR strings (server Decimals) and may
 * be null (divide-by-zero / withheld) — typed as `Numish` and coerced by the
 * Intl formatters, never trusted as a bare number.
 */

import { apiClient } from './client';

export type Numish = number | string | null;

export interface MetricDelta {
  pct: number | null;
  direction: 'up' | 'down' | 'flat';
  is_good: boolean | null;
  is_new: boolean;
}

export interface MetricCard {
  key: string;
  label: string;
  value: Numish;
  format: 'number' | 'currency' | 'percent' | 'ratio';
  delta: MetricDelta | null;
  timeframe: string | null;
}

export interface DataTrust {
  timezone: string;
  last_synced_at: string | null;
  is_provisional: boolean;
  provisional_days: number;
  withheld_reason: string | null;
  sources: string[];
}

export interface Timeframe {
  date_from: string;
  date_to: string;
  compare_from: string | null;
  compare_to: string | null;
  entity_level: string;
}

export interface OverviewResponse {
  title: string;
  timeframe: Timeframe;
  data_trust: DataTrust;
  cards: MetricCard[];
  spend: Numish;
  conversions: Numish;
  conversion_value: Numish;
  impressions: number | null;
  clicks: number | null;
  ctr: Numish;
  cpc: Numish;
  cost_per_conversion: Numish;
  roas: Numish;
  withheld_reason: string | null;
  // BLEND: set when >1 ad platform contributes — conversion-derived blended fields
  // are withheld (non-additive across platforms) while spend/clicks stay.
  conversions_withheld_reason: string | null;
}

export interface SeriesPoint {
  date: string;
  spend: Numish;
  impressions: number;
  clicks: number;
  conversions: Numish;
  conversion_value: Numish;
  ctr: Numish;
  cpc: Numish;
  roas: Numish;
  is_provisional: boolean;
}

export interface SeriesResponse {
  timeframe: Timeframe;
  data_trust: DataTrust;
  points: SeriesPoint[];
  withheld_reason: string | null;
  conversions_withheld_reason: string | null;
}

export interface DayOfWeekCard {
  day_of_week: number;
  label: string;
  spend: Numish;
  impressions: number;
  clicks: number;
  conversions: Numish;
  conversion_value: Numish;
  ctr: Numish;
  cpc: Numish;
  cost_per_conversion: Numish;
  roas: Numish;
}

export interface DayOfWeekResponse {
  timeframe: Timeframe;
  data_trust: DataTrust;
  days: DayOfWeekCard[];
  withheld_reason: string | null;
  conversions_withheld_reason: string | null;
}

export interface BreakdownRow {
  date: string;
  platform: string;
  currency: string | null;
  spend: Numish;
  impressions: number;
  clicks: number;
  conversions: Numish;
  conversion_value: Numish;
  ctr: Numish;
  cpc: Numish;
  cost_per_conversion: Numish;
  roas: Numish;
}

export interface BreakdownResponse {
  timeframe: Timeframe;
  data_trust: DataTrust;
  rows: BreakdownRow[];
}

export interface CampaignRow {
  platform: string;
  connection_id: number;
  campaign_id: string | null;
  name: string | null;
  status: string | null;
  spend: Numish;
  impressions: number;
  clicks: number;
  conversions: Numish;
  conversion_value: Numish;
  ctr: Numish;
  cpc: Numish;
  cost_per_conversion: Numish;
  conversion_rate: Numish;
  roas: Numish;
}

export interface CampaignsResponse {
  timeframe: Timeframe;
  data_trust: DataTrust;
  active_campaigns: number;
  campaigns: CampaignRow[];
}

export interface AllocationSlice {
  platform: string;
  currency: string | null;
  spend: Numish;
  clicks: number;
  impressions: number;
}

export interface AllocationResponse {
  timeframe: Timeframe;
  data_trust: DataTrust;
  slices: AllocationSlice[];
  total_spend: Numish;
  withheld_reason: string | null;
}

export interface SyncRunSummary {
  run_type: string;
  status: string;
  rows_upserted: number;
  started_at: string;
  finished_at: string | null;
  error_class: string | null;
  window_start: string | null;
  window_end: string | null;
}

export interface ConnectionSyncStatus {
  connection_id: number;
  platform: string;
  display_name: string | null;
  external_account_id: string;
  status: 'active' | 'needs_reauth' | 'error' | 'pending' | 'disabled';
  last_synced_at: string | null;
  last_error: string | null;
  failure_count: number;
  reporting_timezone: string;
  currency: string | null;
  latest_run: SyncRunSummary | null;
}

export interface SyncStatusResponse {
  connections: ConnectionSyncStatus[];
}

// ── /analytics (GA4 + GSC) ────────────────────────────────────────────────────
export interface Ga4Totals {
  sessions: number;
  users: number;
  new_users: number;
  engaged_sessions: number;
  // key_events IS GA4's conversion metric (H7) — no separate `conversions`.
  key_events: Numish;
  engagement_rate: Numish;
  is_sampled: boolean; // A11: surface sampling, never hide it
  is_data_golden: boolean; // H3: false ⇒ "(other)" overflow / not finalized
}

export interface Ga4SeriesPoint {
  date: string;
  sessions: number;
  users: number;
}

export interface TrafficSource {
  channel: string;
  sessions: number;
  users: number;
}

export interface TopPage {
  page: string;
  sessions: number;
  users: number;
}

export interface GscTotals {
  clicks: number;
  impressions: number;
  ctr: Numish;
  position: Numish;
}

export interface GscQuery {
  query: string;
  clicks: number;
  impressions: number;
  ctr: Numish;
  position: Numish;
}

export interface GscPage {
  page: string;
  clicks: number;
  impressions: number;
  ctr: Numish;
  position: Numish;
}

export interface AnalyticsResponse {
  timeframe: Timeframe;
  data_trust: DataTrust;
  ga4_configured: boolean; // false → "GA4 Property ID needed" empty state
  gsc_configured: boolean;
  ga4_totals: Ga4Totals | null;
  ga4_series: Ga4SeriesPoint[];
  traffic_sources: TrafficSource[];
  top_pages: TopPage[]; // GA4 top pages (sessions/users)
  gsc_totals: GscTotals | null;
  gsc_queries: GscQuery[];
  gsc_pages: GscPage[]; // GSC top pages (clicks/impressions/position)
}

// ── /social (organic IG/FB) ───────────────────────────────────────────────────
export interface SocialSeriesPoint {
  date: string;
  value: Numish;
}

export interface SocialMetric {
  metric_key: string;
  latest: Numish; // most recent day in the window (null if no data)
  series: SocialSeriesPoint[];
}

export interface SocialPlatform {
  platform: string; // instagram | facebook
  configured: boolean;
  metrics: SocialMetric[];
}

export interface SocialResponse {
  timeframe: Timeframe;
  data_trust: DataTrust;
  platforms: SocialPlatform[];
}

// ── /site-health (PageSpeed) ──────────────────────────────────────────────────
export interface SiteHealthSnapshotOut {
  url: string;
  strategy: string; // mobile | desktop
  captured_date: string;
  performance_score: Numish;
  seo_score: Numish;
  accessibility_score: Numish;
  best_practices_score: Numish;
  lcp_ms: number | null;
  cls: Numish;
  inp_ms: number | null;
}

export interface SiteHealthResponse {
  timeframe: Timeframe;
  data_trust: DataTrust;
  latest: SiteHealthSnapshotOut[];
  trend: SiteHealthSnapshotOut[];
}

// ── /adgroups ─────────────────────────────────────────────────────────────────
export interface AdGroupRow {
  platform: string;
  connection_id: number;
  adgroup_id: string | null;
  campaign_id: string | null;
  name: string | null;
  status: string | null;
  spend: Numish;
  impressions: number;
  clicks: number;
  conversions: Numish;
  conversion_value: Numish;
  ctr: Numish;
  cpc: Numish;
  cost_per_conversion: Numish;
  conversion_rate: Numish;
  roas: Numish;
}

export interface AdGroupsResponse {
  timeframe: Timeframe;
  data_trust: DataTrust;
  adgroups: AdGroupRow[];
}

export interface DateWindow {
  date_from: string;
  date_to: string;
  compare_from?: string;
  compare_to?: string;
  entity_level?: string;
}

function windowParams(w: DateWindow): Record<string, string> {
  const p: Record<string, string> = { date_from: w.date_from, date_to: w.date_to };
  if (w.compare_from) p.compare_from = w.compare_from;
  if (w.compare_to) p.compare_to = w.compare_to;
  if (w.entity_level) p.entity_level = w.entity_level;
  return p;
}

const base = (companyId: number) => `/api/marketing/companies/${companyId}`;

export const getOverview = async (companyId: number, w: DateWindow): Promise<OverviewResponse> =>
  (await apiClient.get<OverviewResponse>(`${base(companyId)}/overview`, { params: windowParams(w) })).data;

export const getSeries = async (companyId: number, w: DateWindow): Promise<SeriesResponse> =>
  (await apiClient.get<SeriesResponse>(`${base(companyId)}/series`, { params: windowParams(w) })).data;

export const getAllocation = async (companyId: number, w: DateWindow): Promise<AllocationResponse> =>
  (await apiClient.get<AllocationResponse>(`${base(companyId)}/allocation`, { params: windowParams(w) })).data;

export const getDayOfWeek = async (companyId: number, w: DateWindow): Promise<DayOfWeekResponse> =>
  (await apiClient.get<DayOfWeekResponse>(`${base(companyId)}/day-of-week`, { params: windowParams(w) })).data;

export const getBreakdown = async (companyId: number, w: DateWindow): Promise<BreakdownResponse> =>
  (await apiClient.get<BreakdownResponse>(`${base(companyId)}/breakdown`, { params: windowParams(w) })).data;

// /campaigns does NOT take entity_level (it forces 'campaign' server-side).
export const getCampaigns = async (companyId: number, w: DateWindow): Promise<CampaignsResponse> =>
  (await apiClient.get<CampaignsResponse>(`${base(companyId)}/campaigns`, {
    params: { date_from: w.date_from, date_to: w.date_to },
  })).data;

// /adgroups forces entity_level='adgroup' server-side (date_from/date_to only).
export const getAdGroups = async (companyId: number, w: DateWindow): Promise<AdGroupsResponse> =>
  (await apiClient.get<AdGroupsResponse>(`${base(companyId)}/adgroups`, {
    params: { date_from: w.date_from, date_to: w.date_to },
  })).data;

// /analytics (GA4 + GSC) takes date_from/date_to only.
export const getAnalytics = async (companyId: number, w: DateWindow): Promise<AnalyticsResponse> =>
  (await apiClient.get<AnalyticsResponse>(`${base(companyId)}/analytics`, {
    params: { date_from: w.date_from, date_to: w.date_to },
  })).data;

// /site-health (PageSpeed snapshots + trend) takes date_from/date_to only.
export const getSiteHealth = async (companyId: number, w: DateWindow): Promise<SiteHealthResponse> =>
  (await apiClient.get<SiteHealthResponse>(`${base(companyId)}/site-health`, {
    params: { date_from: w.date_from, date_to: w.date_to },
  })).data;

// /social (organic Instagram + Facebook) takes date_from/date_to only.
export const getSocial = async (companyId: number, w: DateWindow): Promise<SocialResponse> =>
  (await apiClient.get<SocialResponse>(`${base(companyId)}/social`, {
    params: { date_from: w.date_from, date_to: w.date_to },
  })).data;

export const getSyncStatus = async (companyId: number): Promise<SyncStatusResponse> =>
  (await apiClient.get<SyncStatusResponse>(`${base(companyId)}/sync-status`)).data;

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, waitFor } from '../../../test-utils/renderWithProviders';
import type {
  AnalyticsResponse,
  SiteHealthResponse,
  SyncStatusResponse,
} from '../../../api/marketing';

const getAnalytics = vi.fn();
const getSiteHealth = vi.fn();
const getSyncStatus = vi.fn();

vi.mock('../../../api/marketing', () => ({
  getAnalytics: (...args: unknown[]) => getAnalytics(...args),
  getSiteHealth: (...args: unknown[]) => getSiteHealth(...args),
  getSyncStatus: (...args: unknown[]) => getSyncStatus(...args),
}));

// Imported after the mock is registered.
import { WebsiteAnalyticsTab } from './WebsiteAnalyticsTab';

const TIMEFRAME = {
  date_from: '2026-05-01',
  date_to: '2026-05-31',
  compare_from: null,
  compare_to: null,
  entity_level: 'account',
};
const DATA_TRUST = {
  timezone: 'America/Chicago',
  last_synced_at: null,
  is_provisional: false,
  provisional_days: 0,
  withheld_reason: null,
  sources: [],
};

function analytics(over: Partial<AnalyticsResponse> = {}): AnalyticsResponse {
  return {
    timeframe: TIMEFRAME,
    data_trust: DATA_TRUST,
    ga4_configured: true,
    gsc_configured: true,
    ga4_totals: {
      sessions: 1200,
      users: 900,
      new_users: 400,
      engaged_sessions: 700,
      key_events: '50',
      engagement_rate: 0.58,
      is_sampled: false,
      is_data_golden: true,
    },
    ga4_series: [
      { date: '2026-05-01', sessions: 100, users: 80 },
      { date: '2026-05-02', sessions: 120, users: 95 },
    ],
    traffic_sources: [{ channel: 'Organic Search', sessions: 600, users: 450 }],
    top_pages: [{ page: '/home', sessions: 300, users: 220 }],
    gsc_totals: { clicks: 340, impressions: 9800, ctr: 0.035, position: 12.4 },
    gsc_queries: [{ query: 'crm software', clicks: 50, impressions: 1200, ctr: 0.041, position: 8.2 }],
    gsc_pages: [
      { page: 'https://example.com/pricing', clicks: 30, impressions: 800, ctr: 0.037, position: 6.1 },
    ],
    ...over,
  };
}

function siteHealth(over: Partial<SiteHealthResponse> = {}): SiteHealthResponse {
  return {
    timeframe: TIMEFRAME,
    data_trust: DATA_TRUST,
    latest: [],
    trend: [],
    ...over,
  };
}

const SYNC: SyncStatusResponse = {
  connections: [
    {
      connection_id: 1,
      platform: 'ga4',
      display_name: 'GA4',
      external_account_id: 'props/123',
      status: 'active',
      last_synced_at: '2026-05-31T00:00:00Z',
      last_error: null,
      failure_count: 0,
      reporting_timezone: 'America/Chicago',
      currency: 'USD',
      latest_run: null,
    },
  ],
};

describe('WebsiteAnalyticsTab', () => {
  beforeEach(() => {
    getAnalytics.mockReset();
    getSiteHealth.mockReset();
    getSyncStatus.mockReset();
    getSyncStatus.mockResolvedValue(SYNC);
    getSiteHealth.mockResolvedValue(siteHealth());
  });

  it('renders GA4 KPIs, GSC queries and GSC pages', async () => {
    getAnalytics.mockResolvedValue(analytics());
    renderWithProviders(<WebsiteAnalyticsTab companyId={1} preset="30d" />);

    // Anchor on genuinely unique text: the Users KPI value (sessions=1200 collides
    // with a GSC query's impressions), the GA4 section heading, and the GSC strings.
    // findByText waits for the queries to resolve + re-render.
    expect(await screen.findByText('900')).toBeInTheDocument(); // Users KPI value
    expect(screen.getByText('Google Analytics')).toBeInTheDocument(); // GA4 section rendered
    expect(screen.getByText('crm software')).toBeInTheDocument(); // GSC query
    expect(screen.getByText('https://example.com/pricing')).toBeInTheDocument(); // GSC page
  });

  it('discloses sampling and not-finalized data when flagged', async () => {
    getAnalytics.mockResolvedValue(
      analytics({
        ga4_totals: {
          sessions: 10,
          users: 8,
          new_users: 4,
          engaged_sessions: 6,
          key_events: '1',
          engagement_rate: 0.5,
          is_sampled: true,
          is_data_golden: false,
        },
      }),
    );
    renderWithProviders(<WebsiteAnalyticsTab companyId={1} preset="30d" />);

    expect(await screen.findByText(/Sampled:/)).toBeInTheDocument();
    expect(screen.getByText(/Data still finalizing:/)).toBeInTheDocument();
  });

  it('shows the not-configured empty state when neither GA4 nor GSC is configured', async () => {
    getAnalytics.mockResolvedValue(
      analytics({
        ga4_configured: false,
        gsc_configured: false,
        ga4_totals: null,
        gsc_totals: null,
        ga4_series: [],
        traffic_sources: [],
        top_pages: [],
        gsc_queries: [],
        gsc_pages: [],
      }),
    );
    renderWithProviders(<WebsiteAnalyticsTab companyId={1} preset="30d" />);

    expect(await screen.findByText('No web analytics connected')).toBeInTheDocument();
  });

  it('shows a PageSpeed empty state when there is no snapshot', async () => {
    getAnalytics.mockResolvedValue(analytics());
    renderWithProviders(<WebsiteAnalyticsTab companyId={1} preset="30d" />);

    await waitFor(() => expect(screen.getByText('No PageSpeed snapshot yet.')).toBeInTheDocument());
  });
});

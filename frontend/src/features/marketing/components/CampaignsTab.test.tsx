import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen } from '../../../test-utils/renderWithProviders';
import type {
  AdGroupsResponse,
  CampaignsResponse,
  SyncStatusResponse,
} from '../../../api/marketing';

const getCampaigns = vi.fn();
const getAdGroups = vi.fn();
const getSyncStatus = vi.fn();

vi.mock('../../../api/marketing', () => ({
  getCampaigns: (...args: unknown[]) => getCampaigns(...args),
  getAdGroups: (...args: unknown[]) => getAdGroups(...args),
  getSyncStatus: (...args: unknown[]) => getSyncStatus(...args),
}));

import { CampaignsTab } from './CampaignsTab';

const TIMEFRAME = {
  date_from: '2026-05-01',
  date_to: '2026-05-31',
  compare_from: null,
  compare_to: null,
  entity_level: 'campaign',
};
const DATA_TRUST = {
  timezone: 'America/Chicago',
  last_synced_at: null,
  is_provisional: false,
  provisional_days: 0,
  withheld_reason: null,
  sources: [],
};

const SYNC: SyncStatusResponse = {
  connections: [
    {
      connection_id: 1,
      platform: 'google_ads',
      display_name: 'Google Ads',
      external_account_id: '123-456-7890',
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

const CAMPAIGNS: CampaignsResponse = {
  timeframe: TIMEFRAME,
  data_trust: DATA_TRUST,
  active_campaigns: 3,
  campaigns: [
    {
      platform: 'google_ads',
      connection_id: 1,
      campaign_id: 'c-1',
      name: 'Spring Promo',
      status: 'enabled',
      spend: '500',
      impressions: 12000,
      clicks: 400,
      conversions: '25',
      conversion_value: '2500',
      ctr: 0.033,
      cpc: '1.25',
      cost_per_conversion: '20',
      conversion_rate: 0.0625,
      roas: '5',
    },
  ],
};

const ADGROUPS: AdGroupsResponse = {
  timeframe: { ...TIMEFRAME, entity_level: 'adgroup' },
  data_trust: DATA_TRUST,
  adgroups: [
    {
      platform: 'google_ads',
      connection_id: 1,
      adgroup_id: 'ag-1',
      campaign_id: 'c-1',
      name: 'Brand Terms',
      status: 'enabled',
      spend: '200',
      impressions: 5000,
      clicks: 150,
      conversions: '10',
      conversion_value: '1000',
      ctr: 0.03,
      cpc: '1.33',
      cost_per_conversion: '20',
      conversion_rate: 0.066,
      roas: '5',
    },
  ],
};

describe('CampaignsTab', () => {
  beforeEach(() => {
    getCampaigns.mockReset();
    getAdGroups.mockReset();
    getSyncStatus.mockReset();
    getSyncStatus.mockResolvedValue(SYNC);
    getCampaigns.mockResolvedValue(CAMPAIGNS);
    getAdGroups.mockResolvedValue(ADGROUPS);
  });

  it('renders the active-campaigns KPI, a campaign row and an ad-group row', async () => {
    renderWithProviders(<CampaignsTab companyId={1} preset="30d" />);

    // findByText waits for the queries to resolve (the KPI label renders during the
    // loading state with a "—" value, so assert on the settled count).
    expect(await screen.findByText('3')).toBeInTheDocument(); // active_campaigns count
    expect(screen.getByText('Active Campaigns')).toBeInTheDocument();
    // a campaign row
    expect(await screen.findByText('Spring Promo')).toBeInTheDocument();
    // an ad-group row
    expect(await screen.findByText('Brand Terms')).toBeInTheDocument();
  });

  it('shows empty states when there are no campaigns or ad groups', async () => {
    getCampaigns.mockResolvedValue({ ...CAMPAIGNS, active_campaigns: 0, campaigns: [] });
    getAdGroups.mockResolvedValue({ ...ADGROUPS, adgroups: [] });
    renderWithProviders(<CampaignsTab companyId={1} preset="30d" />);

    expect(await screen.findByText('No campaign activity in this period.')).toBeInTheDocument();
    expect(await screen.findByText('No ad group activity in this period.')).toBeInTheDocument();
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen } from '../../../test-utils/renderWithProviders';
import type { SocialResponse, SyncStatusResponse } from '../../../api/marketing';

const getSocial = vi.fn();
const getSyncStatus = vi.fn();

vi.mock('../../../api/marketing', () => ({
  getSocial: (...args: unknown[]) => getSocial(...args),
  getSyncStatus: (...args: unknown[]) => getSyncStatus(...args),
}));

import { SocialTab } from './SocialTab';

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
const SYNC: SyncStatusResponse = { connections: [] };

function social(over: Partial<SocialResponse> = {}): SocialResponse {
  return {
    timeframe: TIMEFRAME,
    data_trust: DATA_TRUST,
    platforms: [
      {
        platform: 'instagram',
        configured: true,
        metrics: [
          {
            metric_key: 'follower_count',
            latest: '5412',
            series: [
              { date: '2026-05-30', value: '5400' },
              { date: '2026-05-31', value: '5412' },
            ],
          },
          { metric_key: 'reach', latest: '1350', series: [{ date: '2026-05-31', value: '1350' }] },
        ],
      },
    ],
    ...over,
  };
}

describe('SocialTab', () => {
  beforeEach(() => {
    getSocial.mockReset();
    getSyncStatus.mockReset();
    getSyncStatus.mockResolvedValue(SYNC);
  });

  it('renders a platform section with humanized metric KPIs', async () => {
    getSocial.mockResolvedValue(social());
    renderWithProviders(<SocialTab companyId={1} preset="30d" />);

    expect(await screen.findByText('Instagram')).toBeInTheDocument(); // section heading
    // follower_count → "Followers" label; latest 5412 formatted via Intl.
    expect(screen.getAllByText('Followers').length).toBeGreaterThan(0);
    expect(screen.getAllByText('5,412').length).toBeGreaterThan(0);
  });

  it('shows the empty state when no platforms are connected', async () => {
    getSocial.mockResolvedValue(social({ platforms: [] }));
    renderWithProviders(<SocialTab companyId={1} preset="30d" />);

    expect(await screen.findByText('No social accounts connected')).toBeInTheDocument();
  });
});

import { describe, it, expect } from 'vitest';
import { renderWithProviders, screen } from '../../../test-utils/renderWithProviders';
import type { BreakdownRow } from '../../../api/marketing';
import { DailyBreakdownTable } from './DailyBreakdownTable';

function row(over: Partial<BreakdownRow>): BreakdownRow {
  return {
    date: '2026-06-01',
    platform: 'google_ads',
    currency: 'USD',
    spend: '100',
    impressions: 1000,
    clicks: 50,
    conversions: '10',
    conversion_value: '500',
    ctr: null,
    cpc: null,
    cost_per_conversion: null,
    roas: '5',
    ...over,
  };
}

describe('DailyBreakdownTable', () => {
  it('renders Google and Meta rows distinctly with human labels', () => {
    renderWithProviders(
      <DailyBreakdownTable
        rows={[row({ platform: 'google_ads' }), row({ platform: 'meta_ads', spend: '80' })]}
        currency="USD"
      />,
    );
    // per-platform rows are shown (this is where Google vs Meta surface per day)
    expect(screen.getByText('Google Ads')).toBeInTheDocument();
    expect(screen.getByText('Meta')).toBeInTheDocument();
    // conversions are per-platform here (not withheld) so they render
    expect(screen.getAllByText('10').length).toBeGreaterThan(0);
  });

  it('renders an empty state when there are no rows', () => {
    renderWithProviders(<DailyBreakdownTable rows={[]} currency="USD" />);
    expect(screen.getByText('Daily breakdown')).toBeInTheDocument();
    expect(screen.getByText('No spend in this period.')).toBeInTheDocument();
  });
});

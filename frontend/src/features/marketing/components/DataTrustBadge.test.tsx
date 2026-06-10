import { describe, it, expect } from 'vitest';
import { renderWithProviders, screen } from '../../../test-utils/renderWithProviders';
import { DataTrustBadge } from './DataTrustBadge';

describe('DataTrustBadge', () => {
  it('surfaces a reconnect prompt for an expired token, never a silent zero', () => {
    renderWithProviders(
      <DataTrustBadge
        sources={[{ source: 'Google Ads', lastSyncedAt: null, status: 'needs_reauth' }]}
      />,
    );
    expect(screen.getByText('Google Ads')).toBeInTheDocument();
    expect(screen.getByText(/Reconnect needed/)).toBeInTheDocument();
  });

  it('shows real freshness for healthy sources and discloses the timezone', () => {
    renderWithProviders(
      <DataTrustBadge
        sources={[{ source: 'GA4', lastSyncedAt: new Date().toISOString(), status: 'active' }]}
        timezone="America/Chicago"
      />,
    );
    expect(screen.getByText(/Updated just now/)).toBeInTheDocument();
    expect(screen.getByText('All times America/Chicago')).toBeInTheDocument();
  });
});

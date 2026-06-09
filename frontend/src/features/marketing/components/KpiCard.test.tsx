import { describe, it, expect } from 'vitest';
import { renderWithProviders, screen } from '../../../test-utils/renderWithProviders';
import { KpiCard } from './KpiCard';

describe('KpiCard', () => {
  it('renders label, value and timeframe', () => {
    renderWithProviders(
      <KpiCard label="Total Spend" value="$1,234.50" timeframe="vs prior 30 days" />,
    );
    expect(screen.getByText('Total Spend')).toBeInTheDocument();
    expect(screen.getByText('$1,234.50')).toBeInTheDocument();
    expect(screen.getByText('vs prior 30 days')).toBeInTheDocument();
  });

  it('shows an up delta with a sign and an accessible direction (not color alone)', () => {
    renderWithProviders(
      <KpiCard label="ROAS" value="3.20" delta={{ pct: 0.2, sentiment: 'good', isNew: false }} />,
    );
    expect(screen.getByText('+20%')).toBeInTheDocument();
    expect(screen.getByText('up versus the previous period')).toBeInTheDocument();
  });

  it('shows "New" for a zero-baseline instead of a fake percentage', () => {
    renderWithProviders(
      <KpiCard label="Conversions" value="42" delta={{ pct: null, sentiment: 'neutral', isNew: true }} />,
    );
    expect(screen.getByText('New')).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it('renders an em-dash when a delta exists but has no comparable ratio', () => {
    renderWithProviders(
      <KpiCard label="CPC" value="$0.50" delta={{ pct: null, sentiment: 'neutral', isNew: false }} />,
    );
    expect(screen.getByLabelText('no change data')).toBeInTheDocument();
  });

  it('renders a skeleton instead of the value while loading', () => {
    renderWithProviders(<KpiCard label="Clicks" value="999" isLoading />);
    expect(screen.queryByText('999')).not.toBeInTheDocument();
  });
});

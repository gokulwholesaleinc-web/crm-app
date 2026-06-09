import { describe, it, expect } from 'vitest';
import { renderWithProviders, screen, fireEvent } from '../../../test-utils/renderWithProviders';
import { ChartFigure } from './ChartFigure';

const table = {
  columns: [
    { key: 'date', label: 'Date' },
    { key: 'spend', label: 'Spend', numeric: true },
  ],
  rows: [
    { date: 'Jun 1', spend: '$50.00' },
    { date: 'Jun 2', spend: '$60.00' },
  ],
};

describe('ChartFigure', () => {
  it('exposes the insight as the figure aria-label', () => {
    renderWithProviders(
      <ChartFigure title="Daily spend trend">
        <div>chart</div>
      </ChartFigure>,
    );
    expect(screen.getByRole('figure', { name: 'Daily spend trend' })).toBeInTheDocument();
  });

  it('toggles an accessible data table for screen-reader/keyboard users', () => {
    renderWithProviders(
      <ChartFigure title="Daily spend trend" table={table}>
        <div>chart</div>
      </ChartFigure>,
    );
    const toggle = screen.getByRole('button', { name: 'Show data as table' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByText('$50.00')).toBeInTheDocument();
  });

  it('omits the toggle when no table data is provided', () => {
    renderWithProviders(
      <ChartFigure title="Allocation">
        <div>chart</div>
      </ChartFigure>,
    );
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

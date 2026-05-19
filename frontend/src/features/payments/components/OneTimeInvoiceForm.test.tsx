import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, fireEvent } from '../../../test-utils/renderWithProviders';
import { OneTimeInvoiceForm } from './OneTimeInvoiceForm';

function renderForm(overrides: Partial<React.ComponentProps<typeof OneTimeInvoiceForm>> = {}) {
  const defaults = {
    dueDays: 30,
    setDueDays: vi.fn(),
  };
  return renderWithProviders(<OneTimeInvoiceForm {...defaults} {...overrides} />);
}

describe('OneTimeInvoiceForm', () => {
  it('renders Due in selector with the current dueDays selected', () => {
    renderForm({ dueDays: 45 });
    const select = screen.getByLabelText('Due in') as HTMLSelectElement;
    expect(select.value).toBe('45');
  });

  it('calls setDueDays when the due-days select changes', () => {
    const setDueDays = vi.fn();
    renderForm({ setDueDays });
    fireEvent.change(screen.getByLabelText('Due in'), { target: { value: '60' } });
    expect(setDueDays).toHaveBeenCalledWith(60);
  });

  it('does not render explicit payment method checkboxes', () => {
    renderForm();
    expect(screen.queryByRole('checkbox', { name: /card/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /ach/i })).not.toBeInTheDocument();
    expect(screen.getByText(/stripe will offer available payment methods/i)).toBeInTheDocument();
  });

  it('shows all four due-day options', () => {
    renderForm();
    expect(screen.getByRole('option', { name: '15 days' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '30 days' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '45 days' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '60 days' })).toBeInTheDocument();
  });
});

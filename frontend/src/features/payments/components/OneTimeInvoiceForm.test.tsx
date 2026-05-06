import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, fireEvent } from '../../../test-utils/renderWithProviders';
import { OneTimeInvoiceForm } from './OneTimeInvoiceForm';

function renderForm(overrides: Partial<React.ComponentProps<typeof OneTimeInvoiceForm>> = {}) {
  const defaults = {
    dueDays: 30,
    setDueDays: vi.fn(),
    paymentMethodCard: true,
    setPaymentMethodCard: vi.fn(),
    paymentMethodAch: false,
    setPaymentMethodAch: vi.fn(),
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

  it('renders Card checkbox checked when paymentMethodCard is true', () => {
    renderForm({ paymentMethodCard: true });
    const cardCheckbox = screen.getByRole('checkbox', { name: /card/i });
    expect(cardCheckbox).toBeChecked();
  });

  it('renders ACH checkbox unchecked when paymentMethodAch is false', () => {
    renderForm({ paymentMethodAch: false });
    const achCheckbox = screen.getByRole('checkbox', { name: /ach/i });
    expect(achCheckbox).not.toBeChecked();
  });

  it('calls setPaymentMethodCard with false when card checkbox is unchecked', () => {
    const setPaymentMethodCard = vi.fn();
    renderForm({ paymentMethodCard: true, setPaymentMethodCard });
    fireEvent.click(screen.getByRole('checkbox', { name: /card/i }));
    expect(setPaymentMethodCard).toHaveBeenCalledWith(false);
  });

  it('calls setPaymentMethodAch with true when ACH checkbox is checked', () => {
    const setPaymentMethodAch = vi.fn();
    renderForm({ paymentMethodAch: false, setPaymentMethodAch });
    fireEvent.click(screen.getByRole('checkbox', { name: /ach/i }));
    expect(setPaymentMethodAch).toHaveBeenCalledWith(true);
  });

  it('shows all four due-day options', () => {
    renderForm();
    expect(screen.getByRole('option', { name: '15 days' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '30 days' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '45 days' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '60 days' })).toBeInTheDocument();
  });
});

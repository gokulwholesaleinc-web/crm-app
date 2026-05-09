import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, fireEvent } from '../../../test-utils/renderWithProviders';
import { SubscriptionForm, INTERVAL_PRESETS } from './SubscriptionForm';

function renderForm(overrides: Partial<React.ComponentProps<typeof SubscriptionForm>> = {}) {
  const defaults = {
    intervalPreset: 0,
    setIntervalPreset: vi.fn(),
  };
  return renderWithProviders(<SubscriptionForm {...defaults} {...overrides} />);
}

describe('SubscriptionForm', () => {
  it('renders the billing schedule selector', () => {
    renderForm();
    expect(screen.getByLabelText('Billing schedule')).toBeInTheDocument();
  });

  it('renders an option for each interval preset', () => {
    renderForm();
    for (const preset of INTERVAL_PRESETS) {
      expect(screen.getByRole('option', { name: preset.label })).toBeInTheDocument();
    }
  });

  it('reflects the current intervalPreset as the selected option', () => {
    renderForm({ intervalPreset: 2 });
    const select = screen.getByLabelText('Billing schedule') as HTMLSelectElement;
    expect(select.value).toBe('2');
  });

  it('calls setIntervalPreset with the numeric index when selection changes', () => {
    const setIntervalPreset = vi.fn();
    renderForm({ setIntervalPreset });
    fireEvent.change(screen.getByLabelText('Billing schedule'), { target: { value: '3' } });
    expect(setIntervalPreset).toHaveBeenCalledWith(3);
  });

  it('shows the Checkout explanation paragraph', () => {
    renderForm();
    expect(screen.getByText(/stripe will email the customer a checkout link/i)).toBeInTheDocument();
  });

  it('defaults to Monthly (index 0) when intervalPreset is 0', () => {
    renderForm({ intervalPreset: 0 });
    const select = screen.getByLabelText('Billing schedule') as HTMLSelectElement;
    expect(select.value).toBe('0');
    expect(select.options[0]!.text).toBe('Monthly');
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, fireEvent, waitFor } from '../../../../test-utils/renderWithProviders';
import { AccountPreferencesSection } from '../AccountPreferencesSection';
import type { AccountPreferences } from '../../../../api/account';

const updateMutateAsync = vi.fn();

let prefsState: { data: AccountPreferences | undefined; isLoading: boolean; isError: boolean };
let pendingState = { isPending: false };

const DEFAULTS: AccountPreferences = {
  timezone: 'America/Chicago',
  locale: 'en-US',
  date_format: 'MM/DD/YYYY',
  time_format: '12h',
  week_start: 'sunday',
  currency_display: 'USD',
  theme: 'system',
  default_landing: '/dashboard',
};

vi.mock('../../../../hooks/useAccount', () => ({
  useAccountPreferences: () => prefsState,
  useUpdateAccountPreferences: () => ({
    mutateAsync: updateMutateAsync,
    isPending: pendingState.isPending,
  }),
}));

vi.mock('../../../../utils/toast', () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
  showInfo: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  prefsState = { data: { ...DEFAULTS }, isLoading: false, isError: false };
  pendingState = { isPending: false };
  updateMutateAsync.mockResolvedValue({ ...DEFAULTS });
});

describe('AccountPreferencesSection', () => {
  it('renders the timezone select with at least one option and the default selected', () => {
    renderWithProviders(<AccountPreferencesSection />);
    const tz = screen.getByLabelText('Time zone') as HTMLSelectElement;
    expect(tz.options.length).toBeGreaterThan(0);
    expect(tz.value).toBe('America/Chicago');
  });

  it('changing theme enables save and sends the new theme', async () => {
    renderWithProviders(<AccountPreferencesSection />);
    const saveBtn = screen.getByRole('button', { name: /save changes/i });
    expect(saveBtn).toBeDisabled();

    const theme = screen.getByLabelText('Theme') as HTMLSelectElement;
    fireEvent.change(theme, { target: { value: 'dark' } });
    expect(theme.value).toBe('dark');
    expect(saveBtn).not.toBeDisabled();

    fireEvent.click(saveBtn);
    await waitFor(() => {
      expect(updateMutateAsync).toHaveBeenCalledTimes(1);
    });
    expect(updateMutateAsync.mock.calls[0]![0].theme).toBe('dark');
  });

  it('renders all three localization & display field groups', () => {
    renderWithProviders(<AccountPreferencesSection />);
    expect(screen.getByText('Localization')).toBeInTheDocument();
    expect(screen.getByText('Display')).toBeInTheDocument();
    expect(screen.getByText('Defaults')).toBeInTheDocument();
  });
});

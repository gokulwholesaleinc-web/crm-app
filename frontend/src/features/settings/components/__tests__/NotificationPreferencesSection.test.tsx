import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, fireEvent, waitFor } from '../../../../test-utils/renderWithProviders';
import { NotificationPreferencesSection } from '../NotificationPreferencesSection';
import type { NotificationPrefs } from '../../../../api/account';

const updateMutateAsync = vi.fn();

let prefsState: { data: NotificationPrefs | undefined; isLoading: boolean; isError: boolean };
let pendingState = { isPending: false };

const DEFAULT_PREFS: NotificationPrefs = {
  in_app_enabled: true,
  email_enabled: true,
  email_digest: 'instant',
  quiet_hours_enabled: false,
  quiet_hours_start: null,
  quiet_hours_end: null,
  event_matrix: {},
};

vi.mock('../../../../hooks/useAccount', () => ({
  useNotificationPrefs: () => prefsState,
  useUpdateNotificationPrefs: () => ({
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
  prefsState = { data: { ...DEFAULT_PREFS, event_matrix: {} }, isLoading: false, isError: false };
  pendingState = { isPending: false };
  updateMutateAsync.mockResolvedValue({ ...DEFAULT_PREFS });
});

describe('NotificationPreferencesSection', () => {
  it('renders loading spinner while prefs are loading', () => {
    prefsState = { data: undefined, isLoading: true, isError: false };
    renderWithProviders(<NotificationPreferencesSection />);
    expect(screen.getByText('Notifications')).toBeInTheDocument();
  });

  it('renders defaults: master toggles on, all matrix events on', () => {
    renderWithProviders(<NotificationPreferencesSection />);
    expect((screen.getByLabelText('In-app notifications') as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText('Email notifications') as HTMLInputElement).checked).toBe(true);
    // Every event row has both channels ON by default
    expect((screen.getByLabelText('Lead assigned to me: in-app') as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText('Lead assigned to me: email') as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText('Mentioned in a comment: email') as HTMLInputElement).checked).toBe(true);
  });

  it('save button is disabled until something changes', () => {
    renderWithProviders(<NotificationPreferencesSection />);
    const saveBtn = screen.getByRole('button', { name: /save changes/i });
    expect(saveBtn).toBeDisabled();
  });

  it('toggling a matrix checkbox enables save and sends a deep-merged payload', async () => {
    renderWithProviders(<NotificationPreferencesSection />);
    const cb = screen.getByLabelText('Payment received: email') as HTMLInputElement;
    expect(cb.checked).toBe(true);
    fireEvent.click(cb);
    expect(cb.checked).toBe(false);

    const saveBtn = screen.getByRole('button', { name: /save changes/i });
    expect(saveBtn).not.toBeDisabled();
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(updateMutateAsync).toHaveBeenCalledTimes(1);
    });
    const payload = updateMutateAsync.mock.calls[0]![0];
    expect(payload.event_matrix.payment_received).toEqual({ email: false });
    // Other events still untouched
    expect(payload.event_matrix.lead_assigned).toBeUndefined();
    expect(payload.in_app_enabled).toBe(true);
    expect(payload.email_enabled).toBe(true);
  });

  it('disables save button while mutation is pending', () => {
    pendingState = { isPending: true };
    renderWithProviders(<NotificationPreferencesSection />);
    // Touch the form so the button would otherwise be enabled
    fireEvent.click(screen.getByLabelText('Email notifications'));
    expect(screen.getByRole('button', { name: /loading/i })).toBeDisabled();
  });

  it('hides email digest options when email is off', () => {
    renderWithProviders(<NotificationPreferencesSection />);
    expect(screen.getByText(/email digest/i)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Email notifications'));
    expect(screen.queryByText(/email digest/i)).not.toBeInTheDocument();
  });

  it('shows quiet-hours time inputs only when toggle is on', () => {
    renderWithProviders(<NotificationPreferencesSection />);
    expect(screen.queryByLabelText('From')).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/suppress non-urgent/i));
    expect(screen.getByLabelText('From')).toBeInTheDocument();
    expect(screen.getByLabelText('To')).toBeInTheDocument();
  });
});

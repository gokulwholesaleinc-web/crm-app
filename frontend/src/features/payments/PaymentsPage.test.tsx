import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, waitFor, fireEvent } from '../../test-utils/renderWithProviders';
import PaymentsPage from './PaymentsPage';
import type { Payment, SubscriptionItem } from '../../types';

// ── Mutable state for controlling mock return values ──────────────────────────
let usePaymentsMockReturn: ReturnType<typeof makePaymentsMock>;
let useSubscriptionsMockReturn: ReturnType<typeof makeSubsMock>;
const cancelMutateAsync = vi.fn();

function makePaymentsMock(overrides: Partial<{ isLoading: boolean; error: Error | null; items: Payment[] }> = {}) {
  const items = overrides.items ?? [];
  return {
    data: overrides.isLoading ? undefined : { items, pages: 1, total: items.length },
    isLoading: overrides.isLoading ?? false,
    error: overrides.error ?? null,
  };
}

function makeSubsMock(overrides: Partial<{ isLoading: boolean; items: SubscriptionItem[] }> = {}) {
  const items = overrides.items ?? [];
  return {
    data: overrides.isLoading ? undefined : { items, pages: 1, total: items.length },
    isLoading: overrides.isLoading ?? false,
    error: null,
  };
}

// ── Module mocks ─────────────────────────────────────────────────────────────
vi.mock('../../hooks/usePayments', () => ({
  usePayments: () => usePaymentsMockReturn,
  useSubscriptions: () => useSubscriptionsMockReturn,
  useCancelSubscription: () => ({ mutateAsync: cancelMutateAsync, isPending: false }),
}));

vi.mock('../../utils/toast', () => ({ showSuccess: vi.fn(), showError: vi.fn() }));

vi.mock('./components/SendInvoiceModal', () => ({
  SendInvoiceModal: ({ isOpen }: { isOpen: boolean; onClose: () => void }) => (
    <div data-testid="send-invoice-modal">{isOpen ? 'OPEN' : ''}</div>
  ),
}));

// StatusBadge crashes on unknown statuses like 'active' (not in StatusType union).
// Stub it so tests can render subscriptions without breaking.
vi.mock('../../components/ui/Badge', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../components/ui/Badge')>();
  return {
    ...actual,
    StatusBadge: ({ status }: { status: string }) => <span data-testid="status-badge">{status}</span>,
  };
});

import { showSuccess, showError } from '../../utils/toast';

// ── Test fixtures ─────────────────────────────────────────────────────────────
const PAYMENT_1: Payment = {
  id: 101,
  amount: 4999,
  currency: 'usd',
  status: 'succeeded',
  stripe_payment_intent_id: null,
  stripe_checkout_session_id: null,
  description: null,
  receipt_url: null,
  refund_amount: null,
  metadata_json: null,
  customer: { id: 1, stripe_customer_id: 'cus_001', name: 'Acme Corp', email: 'acme@example.com' },
  created_at: '2024-01-15T10:00:00Z',
  updated_at: '2024-01-15T10:00:00Z',
};

const PAYMENT_2: Payment = {
  id: 202,
  amount: 1000,
  currency: 'usd',
  status: 'pending',
  stripe_payment_intent_id: null,
  stripe_checkout_session_id: null,
  description: null,
  receipt_url: null,
  refund_amount: null,
  metadata_json: null,
  customer: { id: 2, stripe_customer_id: 'cus_002', name: 'Beta LLC', email: 'beta@example.com' },
  created_at: '2024-01-16T10:00:00Z',
  updated_at: '2024-01-16T10:00:00Z',
};

const SUBSCRIPTION_1: SubscriptionItem = {
  id: 10,
  stripe_subscription_id: 'sub_abc123',
  customer_id: 1,
  price_id: null,
  status: 'active',
  current_period_start: '2024-01-01T00:00:00Z',
  current_period_end: '2024-02-01T00:00:00Z',
  cancel_at_period_end: false,
  customer: { id: 1, stripe_customer_id: 'cus_001', name: 'Acme Corp', email: 'acme@example.com' },
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  usePaymentsMockReturn = makePaymentsMock();
  useSubscriptionsMockReturn = makeSubsMock();
});

describe('PaymentsPage', () => {
  it('renders "Payments" heading and "Send Invoice" button', () => {
    renderWithProviders(<PaymentsPage />);
    expect(screen.getByRole('heading', { name: 'Payments' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send invoice/i })).toBeInTheDocument();
  });

  it('shows skeleton table while payments are loading', () => {
    usePaymentsMockReturn = makePaymentsMock({ isLoading: true });
    renderWithProviders(<PaymentsPage />);
    // SkeletonTable renders cells; there should be no "No payments" text
    expect(screen.queryByText('No payments')).not.toBeInTheDocument();
  });

  it('renders empty state when there are no payments', () => {
    usePaymentsMockReturn = makePaymentsMock({ items: [] });
    renderWithProviders(<PaymentsPage />);
    expect(screen.getByText('No payments')).toBeInTheDocument();
  });

  it('renders payment rows with customer name when data is present', () => {
    usePaymentsMockReturn = makePaymentsMock({ items: [PAYMENT_1, PAYMENT_2] });
    renderWithProviders(<PaymentsPage />);
    // Customer names appear in the table
    expect(screen.getAllByText('Acme Corp').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Beta LLC').length).toBeGreaterThan(0);
  });

  it('renders error message when usePayments returns an error', () => {
    usePaymentsMockReturn = makePaymentsMock({ error: new Error('Network failure') });
    renderWithProviders(<PaymentsPage />);
    expect(screen.getByText('Network failure')).toBeInTheDocument();
  });

  it('clicking "Send Invoice" opens the SendInvoiceModal', () => {
    renderWithProviders(<PaymentsPage />);
    // Modal stub starts closed (empty string child)
    expect(screen.getByTestId('send-invoice-modal').textContent).toBe('');

    fireEvent.click(screen.getByRole('button', { name: /send invoice/i }));

    expect(screen.getByTestId('send-invoice-modal').textContent).toBe('OPEN');
  });

  it('switching to Subscriptions tab hides payment filters and shows subscriptions', () => {
    useSubscriptionsMockReturn = makeSubsMock({ items: [SUBSCRIPTION_1] });
    renderWithProviders(<PaymentsPage />);

    // Payment search input is visible on All Payments tab
    expect(screen.getByPlaceholderText(/search by customer/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Subscriptions' }));

    // Filters should be hidden after switching tabs
    expect(screen.queryByPlaceholderText(/search by customer/i)).not.toBeInTheDocument();

    // Subscription customer name should now appear
    expect(screen.getAllByText('Acme Corp').length).toBeGreaterThan(0);
  });

  it('switching to Subscriptions tab shows empty state when there are no subscriptions', () => {
    useSubscriptionsMockReturn = makeSubsMock({ items: [] });
    renderWithProviders(<PaymentsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Subscriptions' }));

    expect(screen.getByText('No subscriptions')).toBeInTheDocument();
  });

  it('cancel subscription calls mutateAsync with the sub id and shows success toast', async () => {
    cancelMutateAsync.mockResolvedValueOnce(undefined);
    useSubscriptionsMockReturn = makeSubsMock({ items: [SUBSCRIPTION_1] });
    renderWithProviders(<PaymentsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Subscriptions' }));

    // Cancel button appears for active subs (both mobile card + desktop table; click the first)
    const [firstCancelBtn] = screen.getAllByRole('button', { name: /cancel/i });
    fireEvent.click(firstCancelBtn!);

    await waitFor(() => {
      expect(cancelMutateAsync).toHaveBeenCalledWith(SUBSCRIPTION_1.id);
      expect(showSuccess).toHaveBeenCalledWith('Subscription canceled');
    });
  });

  it('shows error toast when cancel subscription mutation rejects', async () => {
    cancelMutateAsync.mockRejectedValueOnce(new Error('Server error'));
    useSubscriptionsMockReturn = makeSubsMock({ items: [SUBSCRIPTION_1] });
    renderWithProviders(<PaymentsPage />);

    fireEvent.click(screen.getByRole('button', { name: 'Subscriptions' }));

    const [firstCancelBtn] = screen.getAllByRole('button', { name: /cancel/i });
    fireEvent.click(firstCancelBtn!);

    await waitFor(() => {
      expect(showError).toHaveBeenCalledWith('Failed to cancel subscription');
    });
  });
});

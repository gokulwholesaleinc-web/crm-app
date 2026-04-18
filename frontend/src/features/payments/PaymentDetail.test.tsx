import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, waitFor, fireEvent } from '../../test-utils/renderWithProviders';
import PaymentDetailPage from './PaymentDetail';

const usePaymentMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ id: '42' }),
  };
});

vi.mock('../../hooks/usePayments', () => ({
  usePayment: (id: number | undefined) => usePaymentMock(id),
}));

const apiPostMock = vi.fn();
vi.mock('../../api/client', () => ({
  apiClient: {
    post: (...args: unknown[]) => apiPostMock(...args),
  },
}));

const basePayment = {
  id: 42,
  amount: 12345,
  currency: 'USD',
  status: 'succeeded',
  stripe_payment_intent_id: 'pi_abc123',
  stripe_checkout_session_id: 'cs_xyz789',
  payment_method: 'card',
  receipt_url: 'https://stripe.com/receipt/42',
  created_at: '2026-04-01T12:00:00Z',
  updated_at: '2026-04-02T12:00:00Z',
  customer: { name: 'Acme Corp', email: 'acme@example.com', stripe_customer_id: 'cus_001' },
  opportunity: null,
  quote: null,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PaymentDetailPage', () => {
  it('renders loading skeleton while payment is loading', () => {
    usePaymentMock.mockReturnValue({ data: undefined, isLoading: true, error: null });
    const { container } = renderWithProviders(<PaymentDetailPage />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders "Payment not found" on error', () => {
    usePaymentMock.mockReturnValue({ data: undefined, isLoading: false, error: new Error('nope') });
    renderWithProviders(<PaymentDetailPage />);
    expect(screen.getByText('Payment not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to payments/i })).toBeInTheDocument();
  });

  it('renders "Payment not found" when data is missing', () => {
    usePaymentMock.mockReturnValue({ data: undefined, isLoading: false, error: null });
    renderWithProviders(<PaymentDetailPage />);
    expect(screen.getByText('Payment not found')).toBeInTheDocument();
  });

  it('renders payment details, related customer, and action buttons on success', () => {
    usePaymentMock.mockReturnValue({ data: basePayment, isLoading: false, error: null });
    renderWithProviders(<PaymentDetailPage />);

    expect(screen.getByRole('heading', { name: /Payment #42/i })).toBeInTheDocument();
    expect(screen.getByText('pi_abc123')).toBeInTheDocument();
    expect(screen.getByText('cs_xyz789')).toBeInTheDocument();
    expect(screen.getByText('card')).toBeInTheDocument();
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /view receipt/i })).toHaveAttribute('href', 'https://stripe.com/receipt/42');
    expect(screen.getByRole('button', { name: /download invoice/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /resend receipt email/i })).toBeInTheDocument();
  });

  it('shows "No related entities" when customer/opportunity/quote are all missing', () => {
    usePaymentMock.mockReturnValue({
      data: { ...basePayment, customer: null, opportunity: null, quote: null },
      isLoading: false,
      error: null,
    });
    renderWithProviders(<PaymentDetailPage />);
    expect(screen.getByText('No related entities')).toBeInTheDocument();
  });

  it('download invoice button opens /api/payments/:id/invoice in a new tab', () => {
    usePaymentMock.mockReturnValue({ data: basePayment, isLoading: false, error: null });
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    renderWithProviders(<PaymentDetailPage />);
    fireEvent.click(screen.getByRole('button', { name: /download invoice/i }));

    expect(openSpy).toHaveBeenCalledWith('/api/payments/42/invoice', '_blank');
    openSpy.mockRestore();
  });

  it('resend receipt shows success message when apiClient.post resolves', async () => {
    usePaymentMock.mockReturnValue({ data: basePayment, isLoading: false, error: null });
    apiPostMock.mockResolvedValueOnce({ data: { success: true } });

    renderWithProviders(<PaymentDetailPage />);
    fireEvent.click(screen.getByRole('button', { name: /resend receipt email/i }));

    await waitFor(() => {
      expect(apiPostMock).toHaveBeenCalledWith('/api/payments/42/send-receipt');
    });
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/receipt email sent successfully/i);
    });
  });

  it('resend receipt shows failure message when apiClient.post rejects', async () => {
    usePaymentMock.mockReturnValue({ data: basePayment, isLoading: false, error: null });
    apiPostMock.mockRejectedValueOnce(new Error('network down'));

    renderWithProviders(<PaymentDetailPage />);
    fireEvent.click(screen.getByRole('button', { name: /resend receipt email/i }));

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(/failed to send receipt email/i);
    });
  });

  it('disables the resend button while a request is in flight', async () => {
    usePaymentMock.mockReturnValue({ data: basePayment, isLoading: false, error: null });
    let resolvePost: ((value: unknown) => void) | undefined;
    apiPostMock.mockImplementationOnce(() => new Promise((resolve) => { resolvePost = resolve; }));

    renderWithProviders(<PaymentDetailPage />);
    const button = screen.getByRole('button', { name: /resend receipt email/i });
    fireEvent.click(button);

    await waitFor(() => expect(button).toBeDisabled());
    expect(button).toHaveTextContent(/sending/i);

    resolvePost?.({ data: {} });
    await waitFor(() => expect(button).not.toBeDisabled());
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen } from '../../test-utils/renderWithProviders';
import { EntityPaymentsTab } from './EntityPaymentsTab';
import { usePayments, useSubscriptions } from '../../hooks/usePayments';

vi.mock('../../features/payments/PaymentsPage', () => ({
  PaymentForLink: () => <span>Related record</span>,
}));

vi.mock('../../hooks/usePayments', () => ({
  usePayments: vi.fn(),
  useSubscriptions: vi.fn(),
}));

const mockedUsePayments = vi.mocked(usePayments);
const mockedUseSubscriptions = vi.mocked(useSubscriptions);

const emptyPage = {
  items: [],
  total: 0,
  page: 1,
  page_size: 50,
  pages: 0,
};

describe('EntityPaymentsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedUsePayments.mockReturnValue({
      data: emptyPage,
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof usePayments>);
    mockedUseSubscriptions.mockReturnValue({
      data: emptyPage,
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useSubscriptions>);
  });

  it('shows a graceful notice when archived entity filters return 404', () => {
    mockedUsePayments.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: { detail: 'Contact not found', status_code: 404 },
    } as unknown as ReturnType<typeof usePayments>);

    renderWithProviders(<EntityPaymentsTab entityType="contact" entityId={123} />);

    expect(screen.getByText('Payment history unavailable')).toBeInTheDocument();
    expect(screen.getByText(/archived or merged/i)).toBeInTheDocument();
    expect(screen.queryByText('Failed to load payments.')).not.toBeInTheDocument();
  });

  it('keeps non-404 payment errors visible', () => {
    mockedUsePayments.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: { detail: 'Server error', status_code: 500 },
    } as unknown as ReturnType<typeof usePayments>);

    renderWithProviders(<EntityPaymentsTab entityType="contact" entityId={123} />);

    expect(screen.getByText('Failed to load payments.')).toBeInTheDocument();
    expect(screen.queryByText('Payment history unavailable')).not.toBeInTheDocument();
  });
});

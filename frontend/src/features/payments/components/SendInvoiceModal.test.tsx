import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, waitFor, fireEvent } from '../../../test-utils/renderWithProviders';
import { SendInvoiceModal } from './SendInvoiceModal';

const invoiceMutateAsync = vi.fn();
const syncMutateAsync = vi.fn();
const subscriptionMutateAsync = vi.fn();

vi.mock('../../../hooks/usePayments', () => ({
  useStripeCustomers: () => ({
    data: {
      items: [
        { id: 1, stripe_customer_id: 'cus_001', name: 'Acme Corp', email: 'acme@example.com', contact_id: null, company_id: null, created_at: '', updated_at: '' },
        { id: 2, stripe_customer_id: 'cus_002', name: 'Beta LLC', email: 'beta@example.com', contact_id: null, company_id: null, created_at: '', updated_at: '' },
      ],
    },
    isLoading: false,
  }),
  useSyncCustomer: () => ({
    mutateAsync: syncMutateAsync,
    isPending: false,
  }),
  useCreateAndSendInvoice: () => ({
    mutateAsync: invoiceMutateAsync,
    isPending: false,
  }),
  useCreateAndSendSubscription: () => ({
    mutateAsync: subscriptionMutateAsync,
    isPending: false,
  }),
}));

// Stub navigator.clipboard for the copy-to-clipboard feedback path.
Object.assign(navigator, {
  clipboard: { writeText: vi.fn(() => Promise.resolve()) },
});

vi.mock('../../../utils/toast', () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

import { showSuccess, showError } from '../../../utils/toast';

const BASE_PROPS = {
  isOpen: true,
  onClose: vi.fn(),
};

function renderModal(props: Partial<typeof BASE_PROPS & { contactId?: number; contactEmail?: string; defaultAmount?: number }> = {}) {
  return renderWithProviders(<SendInvoiceModal {...BASE_PROPS} {...props} />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SendInvoiceModal', () => {
  it('renders "Send Invoice" title when isOpen is true', () => {
    renderModal();
    // Both the modal title and submit button say "Send Invoice"; target the heading
    expect(screen.getByRole('heading', { name: 'Send Invoice' })).toBeInTheDocument();
  });

  it('does not render modal content when isOpen is false', () => {
    renderModal({ isOpen: false });
    expect(screen.queryByText('Send Invoice')).not.toBeInTheDocument();
  });

  it('renders customer options from useStripeCustomers data', () => {
    renderModal();
    expect(screen.getByRole('option', { name: 'Acme Corp' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Beta LLC' })).toBeInTheDocument();
  });

  it('submit button is disabled when required fields are blank', () => {
    renderModal();
    const submitButton = screen.getByRole('button', { name: /send invoice/i });
    expect(submitButton).toBeDisabled();
  });

  it('submit fires mutateAsync with correct shape and closes on success', async () => {
    invoiceMutateAsync.mockResolvedValueOnce({ invoice_url: null });
    const onClose = vi.fn();

    renderModal({ onClose });

    fireEvent.change(screen.getByLabelText('Customer'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Amount ($)'), { target: { value: '99.99' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Services rendered' } });

    fireEvent.submit(screen.getByLabelText('Amount ($)').closest('form')!);

    await waitFor(() => {
      expect(invoiceMutateAsync).toHaveBeenCalledWith({
        customer_id: 1,
        amount: 99.99,
        description: 'Services rendered',
        due_days: 30,
        payment_method_types: ['card'],
      });
      expect(onClose).toHaveBeenCalledOnce();
    });
  });

  it('shows error and does not submit when no payment method is selected', async () => {
    renderModal();

    fireEvent.change(screen.getByLabelText('Customer'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Amount ($)'), { target: { value: '50' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Test' } });

    // Uncheck card (it's checked by default), ACH remains unchecked
    const cardCheckbox = screen.getByRole('checkbox', { name: /card/i });
    fireEvent.click(cardCheckbox);

    fireEvent.submit(screen.getByLabelText('Amount ($)').closest('form')!);

    await waitFor(() => {
      expect(showError).toHaveBeenCalledWith('Select at least one payment method');
    });
    expect(invoiceMutateAsync).not.toHaveBeenCalled();
  });

  it('copies invoice_url to clipboard on successful one-time submit', async () => {
    const writeSpy = vi.spyOn(navigator.clipboard, 'writeText');
    invoiceMutateAsync.mockResolvedValueOnce({ invoice_url: 'https://invoice.stripe.com/i/test123' });

    renderModal();

    fireEvent.change(screen.getByLabelText('Customer'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Amount ($)'), { target: { value: '100' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Service fee' } });

    fireEvent.submit(screen.getByLabelText('Amount ($)').closest('form')!);

    await waitFor(() => {
      expect(writeSpy).toHaveBeenCalledWith('https://invoice.stripe.com/i/test123');
    });
  });

  it('subscription path posts to subscription endpoint with selected interval preset', async () => {
    subscriptionMutateAsync.mockResolvedValueOnce({
      checkout_session_id: 'cs_test_123',
      checkout_url: 'https://checkout.stripe.com/c/cs_test_123',
      payment_id: 7,
    });
    const onClose = vi.fn();

    renderModal({ onClose });

    // Switch to subscription
    fireEvent.click(screen.getByRole('radio', { name: /subscription/i }));

    fireEvent.change(screen.getByLabelText('Customer'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Amount ($)'), { target: { value: '199' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Monthly retainer' } });

    // Pick "Quarterly" (index 1: month + count 3)
    fireEvent.change(screen.getByLabelText('Billing schedule'), { target: { value: '1' } });

    // Submit button label flips on subscription mode
    fireEvent.click(screen.getByRole('button', { name: /send subscription link/i }));

    await waitFor(() => {
      expect(subscriptionMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          customer_id: 1,
          amount: 199,
          description: 'Monthly retainer',
          interval: 'month',
          interval_count: 3,
        }),
      );
      expect(onClose).toHaveBeenCalledOnce();
    });
    // The one-time path should not have been called.
    expect(invoiceMutateAsync).not.toHaveBeenCalled();
  });

  it('calls showError and does not close when mutation rejects', async () => {
    invoiceMutateAsync.mockRejectedValueOnce(new Error('Network error'));
    const onClose = vi.fn();

    renderModal({ onClose });

    fireEvent.change(screen.getByLabelText('Customer'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Amount ($)'), { target: { value: '75' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Consulting' } });

    fireEvent.submit(screen.getByLabelText('Amount ($)').closest('form')!);

    await waitFor(() => {
      expect(showError).toHaveBeenCalledWith('Failed to create and send invoice');
    });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('does not show Sync Contact button when contactId is not set', () => {
    renderModal();
    expect(screen.queryByRole('button', { name: /sync contact/i })).not.toBeInTheDocument();
  });

  it('shows Sync Contact button when contactId prop is set', () => {
    renderModal({ contactId: 42 });
    expect(screen.getByRole('button', { name: /sync.*(contact|stripe)/i })).toBeInTheDocument();
  });

  it('sync button calls useSyncCustomer.mutateAsync with contact_id and selects returned customer', async () => {
    syncMutateAsync.mockResolvedValueOnce({ id: 2, stripe_customer_id: 'cus_002', name: 'Beta LLC', email: 'beta@example.com' });

    renderModal({ contactId: 42 });

    fireEvent.click(screen.getByRole('button', { name: /sync.*(contact|stripe)/i }));

    await waitFor(() => {
      expect(syncMutateAsync).toHaveBeenCalledWith({ contact_id: 42 });
    });

    await waitFor(() => {
      expect(showSuccess).toHaveBeenCalledWith('Customer synced to Stripe');
    });

    // The returned customer (id=2) should now be selected in the dropdown
    const customerSelect = screen.getByLabelText('Customer') as HTMLSelectElement;
    expect(customerSelect.value).toBe('2');
  });

  it('ACH-only submission sends payment_method_types: [us_bank_account]', async () => {
    invoiceMutateAsync.mockResolvedValueOnce({ invoice_url: null });

    renderModal();

    fireEvent.change(screen.getByLabelText('Customer'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Amount ($)'), { target: { value: '200' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'ACH payment' } });

    // Uncheck card, check ACH
    fireEvent.click(screen.getByRole('checkbox', { name: /card/i }));
    fireEvent.click(screen.getByRole('checkbox', { name: /ach/i }));

    fireEvent.submit(screen.getByLabelText('Amount ($)').closest('form')!);

    await waitFor(() => {
      expect(invoiceMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ payment_method_types: ['us_bank_account'] })
      );
    });
  });

  it('defaultAmount prop prefills the amount input', () => {
    renderModal({ defaultAmount: 149.99 });
    const amountInput = screen.getByLabelText('Amount ($)') as HTMLInputElement;
    expect(amountInput.value).toBe('149.99');
  });
});

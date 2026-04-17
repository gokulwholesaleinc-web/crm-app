import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, waitFor, fireEvent } from '../../../test-utils/renderWithProviders';
import { OnboardingLinkGenerator } from './OnboardingLinkGenerator';
import type { StripeCustomer } from '../../../types/payments';

type StripeCustomersResult = { data: { items: StripeCustomer[] } | undefined; isLoading: boolean };

const linkMutateAsync = vi.fn();
let mockIsPending = false;
const mockStripeCustomers = vi.fn<[], StripeCustomersResult>(() => ({ data: { items: [] }, isLoading: false }));

vi.mock('../../../hooks/usePayments', () => ({
  useCreateOnboardingLink: () => ({ mutateAsync: linkMutateAsync, isPending: mockIsPending }),
  useStripeCustomers: () => mockStripeCustomers(),
}));

vi.mock('../../../utils/toast', () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mockIsPending = false;
  mockStripeCustomers.mockReturnValue({ data: { items: [] }, isLoading: false });
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

describe('OnboardingLinkGenerator', () => {
  it('renders generate button and "No payment method" status when no link and no existing customer', () => {
    renderWithProviders(<OnboardingLinkGenerator contactId={1} />);
    expect(screen.getByRole('button', { name: /generate payment setup link/i })).toBeInTheDocument();
    expect(screen.getByText(/no payment method/i)).toBeInTheDocument();
  });

  it('shows "Payment method on file" when a Stripe customer matching contactId exists', () => {
    const customer: StripeCustomer = {
      id: 1, stripe_customer_id: 'cus_test', email: null, name: null,
      contact_id: 7, company_id: null, created_at: '', updated_at: '',
    };
    mockStripeCustomers.mockReturnValue({ data: { items: [customer] }, isLoading: false });

    renderWithProviders(<OnboardingLinkGenerator contactId={7} />);
    expect(screen.getByText(/payment method on file/i)).toBeInTheDocument();
  });

  it('shows "Payment method on file" when a Stripe customer matching companyId exists', () => {
    const customer: StripeCustomer = {
      id: 2, stripe_customer_id: 'cus_test2', email: null, name: null,
      contact_id: null, company_id: 99, created_at: '', updated_at: '',
    };
    mockStripeCustomers.mockReturnValue({ data: { items: [customer] }, isLoading: false });

    renderWithProviders(<OnboardingLinkGenerator companyId={99} />);
    expect(screen.getByText(/payment method on file/i)).toBeInTheDocument();
  });

  it('clicking generate calls mutateAsync with correct payload including window.location.origin', async () => {
    linkMutateAsync.mockResolvedValueOnce({ url: 'https://stripe.com/onboard/abc' });

    renderWithProviders(<OnboardingLinkGenerator contactId={3} companyId={5} />);
    fireEvent.click(screen.getByRole('button', { name: /generate payment setup link/i }));

    await waitFor(() => expect(linkMutateAsync).toHaveBeenCalledWith({
      contact_id: 3,
      company_id: 5,
      success_url: `${window.location.origin}/payments?setup=success`,
      cancel_url: `${window.location.origin}/payments?setup=canceled`,
    }));
  });

  it('displays the generated link in an input after successful generation', async () => {
    const generatedUrl = 'https://stripe.com/onboard/xyz';
    linkMutateAsync.mockResolvedValueOnce({ url: generatedUrl });

    renderWithProviders(<OnboardingLinkGenerator contactId={3} />);
    fireEvent.click(screen.getByRole('button', { name: /generate payment setup link/i }));

    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: /payment setup link/i })).toHaveValue(generatedUrl)
    );
  });

  it('calls showError when mutation rejects', async () => {
    linkMutateAsync.mockRejectedValueOnce(new Error('stripe error'));

    renderWithProviders(<OnboardingLinkGenerator contactId={3} />);
    fireEvent.click(screen.getByRole('button', { name: /generate payment setup link/i }));

    const toast = await import('../../../utils/toast');
    await waitFor(() =>
      expect(toast.showError).toHaveBeenCalledWith('Failed to generate payment setup link')
    );
  });

  it('copy button calls navigator.clipboard.writeText and shows success toast', async () => {
    const generatedUrl = 'https://stripe.com/onboard/copy-test';
    linkMutateAsync.mockResolvedValueOnce({ url: generatedUrl });

    renderWithProviders(<OnboardingLinkGenerator contactId={3} />);
    fireEvent.click(screen.getByRole('button', { name: /generate payment setup link/i }));
    await waitFor(() => screen.getByRole('button', { name: /copy payment setup link/i }));

    fireEvent.click(screen.getByRole('button', { name: /copy payment setup link/i }));

    const toast = await import('../../../utils/toast');
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(generatedUrl);
      expect(toast.showSuccess).toHaveBeenCalledWith('Link copied to clipboard');
    });
  });

  it('fires onSendViaEmail callback with the generated link when Send via Email is clicked', async () => {
    const generatedUrl = 'https://stripe.com/onboard/email-test';
    linkMutateAsync.mockResolvedValueOnce({ url: generatedUrl });
    const onSendViaEmail = vi.fn();

    renderWithProviders(
      <OnboardingLinkGenerator
        contactId={3}
        contactEmail="test@example.com"
        onSendViaEmail={onSendViaEmail}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /generate payment setup link/i }));
    await waitFor(() => screen.getByRole('button', { name: /send payment setup link via email/i }));

    fireEvent.click(screen.getByRole('button', { name: /send payment setup link via email/i }));
    expect(onSendViaEmail).toHaveBeenCalledWith(generatedUrl);
  });

  it('does not render Send via Email button when onSendViaEmail is provided but contactEmail is missing', async () => {
    linkMutateAsync.mockResolvedValueOnce({ url: 'https://stripe.com/onboard/no-email' });
    const onSendViaEmail = vi.fn();

    renderWithProviders(
      <OnboardingLinkGenerator contactId={3} onSendViaEmail={onSendViaEmail} />
    );
    fireEvent.click(screen.getByRole('button', { name: /generate payment setup link/i }));
    await waitFor(() => screen.getByRole('button', { name: /copy payment setup link/i }));

    expect(screen.queryByRole('button', { name: /send.*via email/i })).not.toBeInTheDocument();
  });

  it('renders correctly with only companyId set (no contactId)', () => {
    renderWithProviders(<OnboardingLinkGenerator companyId={42} />);
    expect(screen.getByRole('button', { name: /generate payment setup link/i })).toBeInTheDocument();
  });

  it('passes undefined contact_id when only companyId is set', async () => {
    linkMutateAsync.mockResolvedValueOnce({ url: 'https://stripe.com/onboard/company' });

    renderWithProviders(<OnboardingLinkGenerator companyId={42} />);
    fireEvent.click(screen.getByRole('button', { name: /generate payment setup link/i }));

    await waitFor(() => expect(linkMutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({ contact_id: undefined, company_id: 42 })
    ));
  });
});

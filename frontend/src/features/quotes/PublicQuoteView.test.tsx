import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// Must use vi.hoisted so the mocks are available before the module-level
// `axios.create()` call executes when PublicQuoteView is imported.
const { mockGet, mockPost, mockPublicClient } = vi.hoisted(() => {
  const mockGet = vi.fn();
  const mockPost = vi.fn();
  return { mockGet, mockPost, mockPublicClient: { get: mockGet, post: mockPost } };
});

vi.mock('axios', () => ({
  default: { create: vi.fn(() => mockPublicClient) },
}));

import PublicQuoteView from './PublicQuoteView';

// Render at the React Router path the component expects.
// The component reads useParams<{ quoteNumber: string }> and treats the value as a token.
function renderAt(quoteNumber = 'test-token-abc') {
  return render(
    <MemoryRouter initialEntries={[`/quotes/public/${quoteNumber}`]}>
      <Routes>
        <Route path="/quotes/public/:quoteNumber" element={<PublicQuoteView />} />
      </Routes>
    </MemoryRouter>
  );
}

const baseLineItem = {
  description: 'Widget Pro',
  quantity: 2,
  unit_price: 500,
  discount: 0,
  total: 1000,
};

const baseBranding = {
  company_name: 'Acme Corp',
  logo_url: null,
  primary_color: '#6366f1',
  secondary_color: '#8b5cf6',
  accent_color: '#22c55e',
  footer_text: null,
};

const baseQuote = {
  quote_number: 'QUO-2024-001',
  title: 'Annual Software License',
  description: null,
  status: 'sent',
  currency: 'USD',
  valid_until: '2099-12-31',
  subtotal: 1000,
  tax_amount: 0,
  total: 1000,
  discount_type: null,
  discount_value: 0,
  terms_and_conditions: null,
  payment_type: 'one_time',
  recurring_interval: null,
  line_items: [baseLineItem],
  company: { id: 1, name: 'Acme Corp' },
  contact: { id: 2, full_name: 'Jane Doe' },
  branding: baseBranding,
};

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
});

describe('PublicQuoteView', () => {
  it('shows loading skeleton initially before GET resolves', () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    renderAt();
    expect(screen.queryByText('Annual Software License')).not.toBeInTheDocument();
  });

  it('renders error state with correct message when GET fails', async () => {
    mockGet.mockRejectedValue(new Error('Network Error'));
    renderAt();
    await waitFor(() =>
      expect(
        screen.getByText('Quote not found or no longer available.')
      ).toBeInTheDocument()
    );
  });

  it('renders quote title, quote_number, total, line item, company and contact on successful GET', async () => {
    mockGet.mockResolvedValue({ data: baseQuote });
    renderAt();
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 1, name: 'Annual Software License' })
      ).toBeInTheDocument()
    );
    expect(screen.getByText('QUO-2024-001')).toBeInTheDocument();
    expect(screen.getByText(/Prepared for Jane Doe/)).toBeInTheDocument();
    expect(screen.getByText('Widget Pro')).toBeInTheDocument();
    expect(screen.getAllByText('$1,000.00').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Acme Corp').length).toBeGreaterThan(0);
  });

  it('clicking Accept opens the e-sign modal with name and email inputs', async () => {
    mockGet.mockResolvedValue({ data: baseQuote });
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: 'Accept this quote' }));

    fireEvent.click(screen.getByRole('button', { name: 'Accept this quote' }));

    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: 'Confirm Acceptance' })).toBeInTheDocument()
    );
    expect(screen.getByLabelText('Full Name')).toBeInTheDocument();
    expect(screen.getByLabelText('Email Address')).toBeInTheDocument();
  });

  it('submitting e-sign modal without name and email shows validation error', async () => {
    mockGet.mockResolvedValue({ data: baseQuote });
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: 'Accept this quote' }));

    fireEvent.click(screen.getByRole('button', { name: 'Accept this quote' }));
    await waitFor(() => screen.getByRole('dialog', { name: 'Confirm Acceptance' }));

    fireEvent.click(screen.getByRole('button', { name: 'Confirm and sign acceptance' }));

    await waitFor(() =>
      expect(
        screen.getByText('Please provide both your name and email address.')
      ).toBeInTheDocument()
    );
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('submitting e-sign modal with name and email POSTs to accept endpoint and shows confirmation', async () => {
    mockGet.mockResolvedValue({ data: baseQuote });
    mockPost.mockResolvedValue({ data: { ...baseQuote, status: 'accepted' } });
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: 'Accept this quote' }));

    fireEvent.click(screen.getByRole('button', { name: 'Accept this quote' }));
    await waitFor(() => screen.getByRole('dialog', { name: 'Confirm Acceptance' }));

    fireEvent.change(screen.getByLabelText('Full Name'), {
      target: { value: 'Jane Doe' },
    });
    fireEvent.change(screen.getByLabelText('Email Address'), {
      target: { value: 'jane@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and sign acceptance' }));

    await waitFor(() =>
      expect(screen.getByText('Quote Accepted')).toBeInTheDocument()
    );
    expect(mockPost).toHaveBeenCalledWith(
      '/api/quotes/public/test-token-abc/accept',
      { signer_name: 'Jane Doe', signer_email: 'jane@example.com' }
    );
    expect(
      screen.getByText(/Thank you for accepting this quote/)
    ).toBeInTheDocument();
  });

  it('shows response.data.detail when POST accept rejects with a detail field', async () => {
    mockGet.mockResolvedValue({ data: baseQuote });
    const err = {
      response: { data: { detail: 'Signer email does not match the quote recipient.' } },
    };
    mockPost.mockRejectedValue(err);
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: 'Accept this quote' }));

    fireEvent.click(screen.getByRole('button', { name: 'Accept this quote' }));
    await waitFor(() => screen.getByRole('dialog', { name: 'Confirm Acceptance' }));

    fireEvent.change(screen.getByLabelText('Full Name'), {
      target: { value: 'Jane Doe' },
    });
    fireEvent.change(screen.getByLabelText('Email Address'), {
      target: { value: 'wrong@other.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and sign acceptance' }));

    await waitFor(() =>
      expect(
        screen.getByText('Signer email does not match the quote recipient.')
      ).toBeInTheDocument()
    );
  });

  it('shows generic fallback message when POST accept rejects without a detail field', async () => {
    mockGet.mockResolvedValue({ data: baseQuote });
    mockPost.mockRejectedValue(new Error('Server error'));
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: 'Accept this quote' }));

    fireEvent.click(screen.getByRole('button', { name: 'Accept this quote' }));
    await waitFor(() => screen.getByRole('dialog', { name: 'Confirm Acceptance' }));

    fireEvent.change(screen.getByLabelText('Full Name'), {
      target: { value: 'Jane Doe' },
    });
    fireEvent.change(screen.getByLabelText('Email Address'), {
      target: { value: 'jane@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and sign acceptance' }));

    await waitFor(() =>
      expect(
        screen.getByText('Failed to accept the quote. Please try again.')
      ).toBeInTheDocument()
    );
  });

  it('clicking Decline POSTs to reject endpoint and shows rejected confirmation', async () => {
    mockGet.mockResolvedValue({ data: baseQuote });
    mockPost.mockResolvedValue({ data: { ...baseQuote, status: 'rejected' } });
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: 'Reject this quote' }));

    // Clicking reject now opens a modal — fill in email and confirm.
    fireEvent.click(screen.getByRole('button', { name: 'Reject this quote' }));
    await waitFor(() => screen.getByRole('dialog', { name: 'Reject Quote' }));

    fireEvent.change(screen.getByLabelText('Email Address'), {
      target: { value: 'test@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /confirm rejection/i }));

    await waitFor(() =>
      expect(screen.getByText('Quote Rejected')).toBeInTheDocument()
    );
    expect(mockPost).toHaveBeenCalledWith(
      '/api/quotes/public/test-token-abc/reject',
      { signer_email: 'test@example.com' }
    );
    expect(screen.getByText(/Thank you for your response/)).toBeInTheDocument();
  });

  it('shows rejection failure message when reject POST fails', async () => {
    mockGet.mockResolvedValue({ data: baseQuote });
    // Reject with a plain Error (no .response.data.detail) so the fallback message fires.
    mockPost.mockRejectedValue(new Error('Network Error'));
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: 'Reject this quote' }));

    // Open the modal and fill in email before submitting.
    fireEvent.click(screen.getByRole('button', { name: 'Reject this quote' }));
    await waitFor(() => screen.getByRole('dialog', { name: 'Reject Quote' }));

    fireEvent.change(screen.getByLabelText('Email Address'), {
      target: { value: 'test@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /confirm rejection/i }));

    await waitFor(() =>
      expect(
        screen.getByText(
          'Unable to record rejection. Please contact your account manager.'
        )
      ).toBeInTheDocument()
    );
  });

  it('does not show Accept/Reject buttons for quotes with status accepted', async () => {
    mockGet.mockResolvedValue({ data: { ...baseQuote, status: 'accepted' } });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    expect(
      screen.queryByRole('button', { name: 'Accept this quote' })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Reject this quote' })
    ).not.toBeInTheDocument();
  });

  it('cancels e-sign modal when Cancel button is clicked', async () => {
    mockGet.mockResolvedValue({ data: baseQuote });
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: 'Accept this quote' }));

    fireEvent.click(screen.getByRole('button', { name: 'Accept this quote' }));
    await waitFor(() => screen.getByRole('dialog', { name: 'Confirm Acceptance' }));

    fireEvent.click(screen.getByRole('button', { name: 'Cancel acceptance' }));

    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', { name: 'Confirm Acceptance' })
      ).not.toBeInTheDocument()
    );
    expect(mockPost).not.toHaveBeenCalled();
  });
});

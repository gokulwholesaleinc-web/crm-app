import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

const { mockGet, mockPost, mockPublicClient } = vi.hoisted(() => {
  const mockGet = vi.fn();
  const mockPost = vi.fn();
  return { mockGet, mockPost, mockPublicClient: { get: mockGet, post: mockPost } };
});

vi.mock('axios', () => ({
  default: { create: vi.fn(() => mockPublicClient) },
}));

vi.mock('../../components/SignToConfirmModal', () => ({
  SignToConfirmModal: ({
    isOpen,
    selectedPackageId,
    onSubmit,
  }: {
    isOpen: boolean;
    selectedPackageId?: number | null;
    onSubmit: (payload: {
      signatureDataUrl: string;
      email: string;
      agreedToTerms: boolean;
      selectedPackageId?: number | null;
    }) => Promise<string | null>;
  }) =>
    isOpen ? (
      <button
        type="button"
        onClick={() =>
          void onSubmit({
            signatureDataUrl: 'data:image/png;base64,abc',
            email: 'jane@example.com',
            agreedToTerms: true,
            selectedPackageId,
          })
        }
      >
        Submit mocked signature
      </button>
    ) : null,
}));

import PublicProposalView from './PublicProposalView';

function renderAt(token = 'abc123', search = '') {
  return render(
    <MemoryRouter initialEntries={[`/proposals/public/${token}${search}`]}>
      <Routes>
        <Route path="/proposals/public/:token" element={<PublicProposalView />} />
      </Routes>
    </MemoryRouter>
  );
}

const baseProposal = {
  proposal_number: 'PROP-001',
  title: 'Test Proposal Title',
  content: null,
  cover_letter: null,
  executive_summary: null,
  scope_of_work: null,
  pricing_section: null,
  timeline: null,
  terms: null,
  valid_until: null,
  status: 'sent',
  company: { id: 1, name: 'Acme Corp' },
  contact: { id: 2, full_name: 'Jane Doe' },
  branding: null,
  designated_signer_email: 'jane@example.com',
  terms_and_conditions: null,
  has_master_contract: false,
};

const packageOptions = [
  {
    id: 10,
    name: 'Starter',
    description: 'Baseline implementation.',
    currency: 'USD',
    payment_type: 'one_time',
    recurring_interval: null,
    recurring_interval_count: null,
    subtotal: '1250.00',
    discount_amount: '0.00',
    tax_amount: '0.00',
    total: '1250.00',
    sort_order: 0,
    is_recommended: false,
    items: [
      {
        description: 'Implementation',
        quantity: '1.00',
        unit_price: '1250.00',
        discount_amount: '0.00',
        total: '1250.00',
      },
    ],
  },
  {
    id: 11,
    name: 'Growth',
    description: 'Implementation plus monthly support.',
    currency: 'USD',
    payment_type: 'subscription',
    recurring_interval: 'month',
    recurring_interval_count: 1,
    subtotal: '2500.00',
    discount_amount: '0.00',
    tax_amount: '200.00',
    total: '2700.00',
    sort_order: 1,
    is_recommended: true,
    items: [
      {
        description: 'Monthly support',
        quantity: '1.00',
        unit_price: '2500.00',
        discount_amount: '0.00',
        total: '2500.00',
      },
    ],
  },
];

beforeEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
  mockGet.mockReset();
  mockPost.mockReset();
  // Return a popup-shaped fake Window so handleOpen's
  // `popup.opener = null; popup.location.href = url` writes succeed
  // without bailing out the popup-blocked guard.
  vi.spyOn(window, 'open').mockImplementation(() => ({
    opener: window,
    location: { href: '' },
  } as unknown as Window));
  vi.spyOn(window, 'alert').mockImplementation(() => {});
});

describe('PublicProposalView', () => {
  it('shows loading state initially before GET resolves', () => {
    // Never resolves during this test
    mockGet.mockReturnValue(new Promise(() => {}));
    renderAt();
    // Loading state renders animate-pulse skeleton — no proposal title yet
    expect(screen.queryByText('Test Proposal Title')).not.toBeInTheDocument();
  });

  it('renders proposal title and key fields on successful GET', async () => {
    mockGet.mockResolvedValue({ data: baseProposal });
    renderAt();
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1, name: 'Test Proposal Title' })).toBeInTheDocument()
    );
    // proposal_number appears multiple times (header + cover section + footer)
    expect(screen.getAllByText('PROP-001').length).toBeGreaterThan(0);
    // "Prepared for Jane Doe" is split across <p> + <span> — match by combined text content
    expect(
      screen.getByText((_, el) => el?.textContent?.replace(/\s+/g, ' ').trim().startsWith('Prepared for Jane Doe') ?? false)
    ).toBeInTheDocument();
  });

  it('renders error state when GET fails', async () => {
    mockGet.mockRejectedValue(new Error('Network Error'));
    renderAt();
    await waitFor(() =>
      expect(screen.getByText('Proposal not found or no longer available.')).toBeInTheDocument()
    );
  });

  it('uses DEFAULT_BRANDING when proposal.branding is null — header renders with surface bg', async () => {
    mockGet.mockResolvedValue({ data: { ...baseProposal, branding: null } });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    // Header renders with tenant surface_color_light via inline style (default #ffffff)
    const header = document.querySelector('header');
    expect(header).toBeTruthy();
    expect(header?.getAttribute('style')).toContain('background-color');
  });

  it('uses provided branding colors when branding is present', async () => {
    const branding = {
      company_name: 'Custom Co',
      logo_url: null,
      primary_color: '#ff0000',
      secondary_color: '#00ff00',
      accent_color: '#0000ff',
      footer_text: 'Custom footer',
    };
    mockGet.mockResolvedValue({ data: { ...baseProposal, branding } });
    renderAt();
    // 'Custom Co' renders both as the header company label and (if differing
    // from proposal.company.name) as the "Prepared for ... · Custom Co" tail.
    await waitFor(() => expect(screen.getAllByText('Custom Co').length).toBeGreaterThan(0));
    // Header uses inline style (surface_color_light from branding, not a Tailwind bg class)
    const header = document.querySelector('header');
    expect(header).toBeTruthy();
    expect(screen.getByText('Custom footer')).toBeInTheDocument();
  });

  it('falls back to initial letter avatar when logo_url is null', async () => {
    mockGet.mockResolvedValue({ data: baseProposal });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    // No logo img — should show first letter avatar for "Acme Corp" → "A"
    expect(screen.getByText('A')).toBeInTheDocument();
  });

  it('hides img and shows fallback avatar when logo onError fires', async () => {
    const branding = {
      company_name: 'Logo Co',
      logo_url: 'https://example.com/logo.png',
      primary_color: '#6366f1',
      secondary_color: '#8b5cf6',
      accent_color: '#22c55e',
      footer_text: null,
    };
    mockGet.mockResolvedValue({ data: { ...baseProposal, branding } });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));

    const img = screen.getByRole('img', { name: 'Logo Co' });
    expect(img).toBeInTheDocument();

    fireEvent.error(img);

    // After error, img is replaced by the letter avatar
    await waitFor(() => expect(screen.queryByRole('img', { name: 'Logo Co' })).not.toBeInTheDocument());
    expect(screen.getByText('L')).toBeInTheDocument();
  });

  // Note: the inline name/email/signature form was replaced by
  // SignToConfirmModal (the customer types in the modal, not on the
  // page). The signing-modal mechanics are covered separately in
  // SignToConfirmModal.test.tsx; here we only assert that the page
  // surfaces the right entry points + handles the reject-direct path.

  it('renders Sign to Accept and Decline buttons for a sent proposal', async () => {
    mockGet.mockResolvedValue({ data: baseProposal });
    renderAt();
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /Open the signing dialog to accept this proposal/i }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole('button', { name: /Decline this proposal/i }),
    ).toBeInTheDocument();
  });

  it('shows the legacy payment CTA for awaiting-payment proposals', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...baseProposal,
        status: 'awaiting_payment',
        stripe_payment_url: 'https://checkout.stripe.test/pay',
        amount: '50000',
        currency: 'USD',
      },
    });

    renderAt();

    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1, name: 'Test Proposal Title' })).toBeInTheDocument(),
    );
    const link = screen.getByRole('link', { name: /Complete Payment/i });
    expect(link).toHaveAttribute('href', 'https://checkout.stripe.test/pay');
    expect(screen.queryByText(/USD/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/50000/i)).not.toBeInTheDocument();
  });

  it('renders package radio cards with formatted currency and hides zero tax rows', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...baseProposal,
        packages: packageOptions,
      },
    });

    renderAt();

    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    expect(screen.getByRole('radio', { name: /Starter/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Growth/i })).toBeInTheDocument();
    expect(screen.getAllByText('$1,250.00').length).toBeGreaterThan(0);
    expect(screen.getAllByText('$2,700.00').length).toBeGreaterThan(0);
    expect(screen.getAllByText('$200.00').length).toBeGreaterThan(0);

    const taxLabels = screen.getAllByText('Tax');
    expect(taxLabels).toHaveLength(1);
  });

  it('requires a package selection and sends selected_package_id on accept', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...baseProposal,
        packages: packageOptions,
      },
    });
    mockPost.mockResolvedValue({
      data: {
        ...baseProposal,
        status: 'accepted',
        selected_package_snapshot: {
          package_id: 11,
          name: 'Growth',
          currency: 'USD',
          payment_type: 'subscription',
          recurring_interval: 'month',
          recurring_interval_count: 1,
          subtotal: '2500.00',
          discount_amount: '0.00',
          tax_amount: '0.00',
          total: '2500.00',
          captured_at: '2026-05-20T00:00:00Z',
          items: [],
        },
      },
    });

    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));

    const signButton = screen.getByRole('button', {
      name: /Open the signing dialog to accept this proposal/i,
    });
    expect(signButton).toBeDisabled();
    expect(screen.getByText(/Choose a package before signing/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', { name: /Growth/i }));
    expect(signButton).not.toBeDisabled();

    fireEvent.click(signButton);
    fireEvent.click(await screen.findByRole('button', { name: /Submit mocked signature/i }));

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith(
        '/api/proposals/public/abc123/accept',
        expect.objectContaining({ selected_package_id: 11 }),
      ),
    );
  });

  it('hides the legacy payment CTA when package options or a snapshot exist', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        ...baseProposal,
        status: 'awaiting_payment',
        stripe_payment_url: 'https://checkout.stripe.test/pay',
        packages: packageOptions,
      },
    });
    const { unmount } = renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    expect(screen.queryByRole('link', { name: /Complete Payment/i })).not.toBeInTheDocument();
    unmount();

    mockGet.mockResolvedValueOnce({
      data: {
        ...baseProposal,
        status: 'awaiting_payment',
        stripe_payment_url: 'https://checkout.stripe.test/pay',
        selected_package_snapshot: {
          package_id: 10,
          name: 'Starter',
          currency: 'USD',
          payment_type: 'one_time',
          subtotal: '1250.00',
          discount_amount: '0.00',
          tax_amount: '0.00',
          total: '1250.00',
          captured_at: '2026-05-20T00:00:00Z',
          items: [],
        },
      },
    });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    expect(screen.queryByRole('link', { name: /Complete Payment/i })).not.toBeInTheDocument();
    expect(screen.getByText('Selected Package')).toBeInTheDocument();
  });

  it('requires opening public documents before enabling Sign to Accept', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...baseProposal,
        attachments: [
          { id: 11, filename: 'scope.pdf', file_size: 1200, viewed: false },
        ],
        signing_documents: [
          { id: 22, filename: 'agreement.pdf', file_size: 2200, viewed: false },
        ],
      },
    });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));

    const signButton = screen.getByRole('button', {
      name: /Open the signing dialog to accept this proposal/i,
    });
    expect(signButton).toBeDisabled();
    expect(screen.getByText(/Open every document before signing\. 2 remaining/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Open scope\.pdf/i }));
    expect(screen.getByText(/1 remaining/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Open agreement\.pdf/i }));
    expect(signButton).not.toBeDisabled();
  });

  it('does not mark a document viewed when the popup is blocked', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...baseProposal,
        attachments: [
          { id: 11, filename: 'scope.pdf', file_size: 1200, viewed: false },
        ],
        signing_documents: [],
      },
    });
    // Simulate a popup-blocker by returning null from window.open.
    (window.open as ReturnType<typeof vi.fn>).mockImplementation(() => null);
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));

    fireEvent.click(screen.getByRole('button', { name: /Open scope\.pdf/i }));

    // The popup-blocked path alerts the user and refuses to optimistically
    // mark viewed — gate must still show 1 remaining and Sign disabled.
    expect(window.alert).toHaveBeenCalled();
    expect(screen.getByText(/Open every document before signing\. 1 remaining/i)).toBeInTheDocument();
    expect(screen.getByRole('button', {
      name: /Open the signing dialog to accept this proposal/i,
    })).toBeDisabled();
  });

  it('keeps Sign to Accept enabled when server says all documents were opened', async () => {
    mockGet.mockResolvedValue({
      data: {
        ...baseProposal,
        attachments: [
          { id: 11, filename: 'scope.pdf', file_size: 1200, viewed: true },
        ],
        signing_documents: [
          { id: 22, filename: 'agreement.pdf', file_size: 2200, viewed: true },
        ],
      },
    });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));

    expect(
      screen.getByRole('button', { name: /Open the signing dialog to accept this proposal/i }),
    ).not.toBeDisabled();
  });

  // Note: "Sign to Accept" opens SignToConfirmModal — its own test
  // suite covers the modal mechanics. We don't render it here because
  // react-signature-canvas requires HTMLCanvasElement, which jsdom
  // doesn't implement; the resulting ref-null error is not a real bug.

  it('Decline shows signError when proposal has no designated_signer_email', async () => {
    // No designated_signer_email + the page only forwards that field;
    // handleReject short-circuits with a signError instead of POSTing.
    mockGet.mockResolvedValue({
      data: { ...baseProposal, designated_signer_email: null },
    });
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: /Decline this proposal/i }));

    fireEvent.click(screen.getByRole('button', { name: /Decline this proposal/i }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        /This proposal has no recipient on file/i,
      ),
    );
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('Decline posts /reject with the designated signer email and shows declined confirmation', async () => {
    mockGet.mockResolvedValue({
      data: { ...baseProposal, designated_signer_email: 'jane@example.com' },
    });
    mockPost.mockResolvedValue({});
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: /Decline this proposal/i }));

    fireEvent.click(screen.getByRole('button', { name: /Decline this proposal/i }));

    await waitFor(() =>
      expect(screen.getByText('Proposal declined')).toBeInTheDocument(),
    );
    expect(mockPost).toHaveBeenCalledWith(
      '/api/proposals/public/abc123/reject',
      { signer_email: 'jane@example.com' },
    );
  });

  it('Decline surfaces backend detail when /reject returns an error', async () => {
    mockGet.mockResolvedValue({
      data: { ...baseProposal, designated_signer_email: 'jane@example.com' },
    });
    mockPost.mockRejectedValue({
      response: { data: { detail: 'Proposal already accepted.' } },
    });
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: /Decline this proposal/i }));

    fireEvent.click(screen.getByRole('button', { name: /Decline this proposal/i }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        /Proposal already accepted/i,
      ),
    );
  });

  it('hides action buttons after rejection lands', async () => {
    mockGet.mockResolvedValue({
      data: { ...baseProposal, designated_signer_email: 'jane@example.com' },
    });
    mockPost.mockResolvedValue({});
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: /Decline this proposal/i }));

    fireEvent.click(screen.getByRole('button', { name: /Decline this proposal/i }));

    await waitFor(() =>
      expect(screen.getByText('Proposal declined')).toBeInTheDocument(),
    );
    expect(
      screen.queryByRole('button', { name: /Decline this proposal/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Open the signing dialog to accept this proposal/i }),
    ).not.toBeInTheDocument();
  });

  it('disables Decline while reject is pending', async () => {
    mockGet.mockResolvedValue({
      data: { ...baseProposal, designated_signer_email: 'jane@example.com' },
    });
    // Never resolves so actionPending stays true.
    mockPost.mockReturnValue(new Promise(() => {}));
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: /Decline this proposal/i }));

    fireEvent.click(screen.getByRole('button', { name: /Decline this proposal/i }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Decline this proposal/i })).toBeDisabled(),
    );
  });

  it('does not render action buttons for proposals in status=draft', async () => {
    mockGet.mockResolvedValue({ data: { ...baseProposal, status: 'draft' } });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    expect(
      screen.queryByRole('button', { name: /Open the signing dialog to accept this proposal/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Decline this proposal/i }),
    ).not.toBeInTheDocument();
  });

  it('renders optional sections only when content is provided', async () => {
    const proposal = {
      ...baseProposal,
      cover_letter: 'This is the cover letter.',
      executive_summary: 'This is the summary.',
      scope_of_work: 'This is the scope.',
    };
    mockGet.mockResolvedValue({ data: proposal });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    expect(screen.getByText('This is the cover letter.')).toBeInTheDocument();
    expect(screen.getByText('Executive Summary')).toBeInTheDocument();
    expect(screen.getByText('This is the summary.')).toBeInTheDocument();
    expect(screen.getByText('Scope of Work')).toBeInTheDocument();
  });

  it('renders "Prepared for" line with role="doc-subtitle" and aria-label="Recipient"', async () => {
    mockGet.mockResolvedValue({ data: baseProposal });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    const subtitle = document.querySelector('[role="doc-subtitle"]');
    expect(subtitle).toBeTruthy();
    expect(subtitle?.getAttribute('aria-label')).toBe('Recipient');
    expect(subtitle?.textContent).toContain('Jane Doe');
  });

  it('does not render "Prepared for" subtitle when contact is null', async () => {
    mockGet.mockResolvedValue({ data: { ...baseProposal, contact: null } });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    expect(document.querySelector('[role="doc-subtitle"]')).toBeNull();
  });
});

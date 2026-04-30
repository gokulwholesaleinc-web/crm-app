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

import PublicProposalView from './PublicProposalView';

function renderAt(token = 'abc123') {
  return render(
    <MemoryRouter initialEntries={[`/proposals/public/${token}`]}>
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
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockReset();
  mockPost.mockReset();
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

  it('uses DEFAULT_BRANDING when proposal.branding is null — header stays bg-white', async () => {
    mockGet.mockResolvedValue({ data: { ...baseProposal, branding: null } });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    // Header is intentionally static bg-white (not branded) — confirm class present
    const header = document.querySelector('header');
    expect(header).toHaveClass('bg-white');
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
    // Header stays bg-white — branding accent is applied to avatar + inline-style accents
    const header = document.querySelector('header');
    expect(header).toHaveClass('bg-white');
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

  it('shows signError when accept clicked with missing name and email', async () => {
    mockGet.mockResolvedValue({ data: baseProposal });
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: 'Accept this proposal' }));

    fireEvent.click(screen.getByRole('button', { name: 'Accept this proposal' }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Please enter your full name and email address.'
      )
    );
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('shows signError when only name is filled and accept is clicked', async () => {
    mockGet.mockResolvedValue({ data: baseProposal });
    renderAt();
    await waitFor(() => screen.getByLabelText('Full name'));

    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Jane Doe' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accept this proposal' }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Please enter your full name and email address.'
      )
    );
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('calls POST accept with signer payload and shows accepted confirmation', async () => {
    mockGet.mockResolvedValue({ data: baseProposal });
    // Accept handler sets `proposal = response.data`, so the mock MUST
    // return a populated `data` payload — otherwise the component renders
    // its "Proposal not found" empty state and the assertions below fail.
    mockPost.mockResolvedValue({ data: { ...baseProposal, status: 'accepted' } });
    renderAt();
    await waitFor(() => screen.getByLabelText('Full name'));

    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Jane Doe' } });
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'jane@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accept this proposal' }));

    await waitFor(() => expect(screen.getByText('Proposal accepted')).toBeInTheDocument());
    expect(mockPost).toHaveBeenCalledWith('/api/proposals/public/abc123/accept', {
      signer_name: 'Jane Doe',
      signer_email: 'jane@example.com',
    });
    expect(screen.getByText(/will be in touch shortly/)).toBeInTheDocument();
  });

  it('calls POST reject and shows rejected confirmation', async () => {
    mockGet.mockResolvedValue({ data: baseProposal });
    mockPost.mockResolvedValue({});
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: 'Decline this proposal' }));

    // Fill email — required by handleReject gate
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'jane@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Decline this proposal' }));

    await waitFor(() => expect(screen.getByText('Proposal declined')).toBeInTheDocument());
    expect(mockPost).toHaveBeenCalledWith('/api/proposals/public/abc123/reject', {
      signer_email: expect.any(String),
    });
    expect(screen.getByText(/Thank you for your response/)).toBeInTheDocument();
  });

  it('hides signer form and action buttons after actionDone is set', async () => {
    mockGet.mockResolvedValue({ data: baseProposal });
    mockPost.mockResolvedValue({ data: { ...baseProposal, status: 'accepted' } });
    renderAt();
    await waitFor(() => screen.getByLabelText('Full name'));

    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Jane Doe' } });
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'jane@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accept this proposal' }));

    await waitFor(() => expect(screen.getByText('Proposal accepted')).toBeInTheDocument());
    expect(screen.queryByLabelText('Full name')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Accept this proposal' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Decline this proposal' })).not.toBeInTheDocument();
  });

  it('disables action buttons while actionPending', async () => {
    mockGet.mockResolvedValue({ data: baseProposal });
    // Never resolves so actionPending stays true
    mockPost.mockReturnValue(new Promise(() => {}));
    renderAt();
    await waitFor(() => screen.getByLabelText('Full name'));

    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Jane Doe' } });
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'jane@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accept this proposal' }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Accept this proposal' })).toBeDisabled()
    );
    expect(screen.getByRole('button', { name: 'Decline this proposal' })).toBeDisabled();
  });

  it('shows backend detail message when accept POST returns an error with detail', async () => {
    mockGet.mockResolvedValue({ data: baseProposal });
    const err = { response: { data: { detail: 'Signer email does not match contact.' } } };
    mockPost.mockRejectedValue(err);
    renderAt();
    await waitFor(() => screen.getByLabelText('Full name'));

    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Jane Doe' } });
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'jane@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Accept this proposal' }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Signer email does not match contact.')
    );
  });

  it('does not show action section for proposals with status draft', async () => {
    mockGet.mockResolvedValue({ data: { ...baseProposal, status: 'draft' } });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    expect(screen.queryByRole('button', { name: 'Accept this proposal' })).not.toBeInTheDocument();
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
});

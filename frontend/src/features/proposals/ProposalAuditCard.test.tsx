import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import type { Proposal } from '../../types';
import { ProposalAuditCard } from './ProposalAuditCard';
import { server } from '../../test-setup';

const signedProposal = {
  id: 1,
  proposal_number: 'PROP-001',
  title: 'Signed proposal',
  status: 'accepted',
  view_count: 1,
  payment_type: 'one_time',
  currency: 'USD',
  created_at: '2026-05-20T00:00:00Z',
  updated_at: '2026-05-20T00:00:00Z',
  signed_at: '2026-05-20T18:00:00Z',
  agreed_to_terms_at: '2026-05-20T18:00:00Z',
  signer_name: 'Jane Doe',
  signer_email: 'jane@example.com',
  acceptance_method: 'drawn_signature',
  esign_disclosure_version: '2026-05-27.sign-to-confirm.v2',
  esign_disclosure_snapshot:
    'By drawing and submitting your signature, you confirm acceptance.\n\nWe record your name, email, IP, and timestamp.',
  terms_and_conditions_snapshot: 'These are the per-proposal terms.',
  views: [],
} as Proposal;

const SIGNATURE_PATH = '/api/proposals/:id/signature';

describe('ProposalAuditCard', () => {
  beforeEach(() => {
    // The card fetches the signature image on mount; default to a present
    // PNG so the global onUnhandledRequest:'error' guard stays satisfied.
    server.use(
      http.get(SIGNATURE_PATH, () =>
        new HttpResponse(new Uint8Array([1, 2, 3]).buffer, {
          headers: { 'Content-Type': 'image/png' },
        }),
      ),
    );
  });

  it('renders captured signer details', () => {
    render(<ProposalAuditCard proposal={signedProposal} />);

    expect(screen.getByText('E-signature captured')).toBeInTheDocument();
    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText('jane@example.com')).toBeInTheDocument();
  });

  it('renders the drawn signature image and durable evidence', async () => {
    render(<ProposalAuditCard proposal={signedProposal} />);

    // Signature image loads asynchronously via an object URL.
    expect(
      await screen.findByAltText('Signature drawn by Jane Doe'),
    ).toBeInTheDocument();

    expect(screen.getByText('Drawn signature')).toBeInTheDocument();
    expect(
      screen.getByText('View consent record (v2026-05-27.sign-to-confirm.v2)'),
    ).toBeInTheDocument();
    // Disclosure + terms snapshots are in the DOM (inside <details>).
    expect(
      screen.getByText(/you confirm acceptance/),
    ).toBeInTheDocument();
    expect(
      screen.getByText('These are the per-proposal terms.'),
    ).toBeInTheDocument();
  });

  it('hides the signature image when none was captured (404)', async () => {
    server.use(
      http.get(SIGNATURE_PATH, () => new HttpResponse(null, { status: 404 })),
    );

    render(<ProposalAuditCard proposal={signedProposal} />);

    // Metadata still renders even with no signature artifact.
    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.queryByAltText('Signature drawn by Jane Doe'),
      ).not.toBeInTheDocument();
    });
    // A 404 is the expected "no signature drawn" case — no error notice.
    expect(
      screen.queryByText(/signature image couldn’t be loaded/i),
    ).not.toBeInTheDocument();
  });

  it('surfaces a notice when the signature fetch fails (non-404)', async () => {
    server.use(
      http.get(SIGNATURE_PATH, () => new HttpResponse(null, { status: 500 })),
    );

    render(<ProposalAuditCard proposal={signedProposal} />);

    // The legal artifact is unreachable, not absent — operator must be told.
    expect(
      await screen.findByText(/signature image couldn’t be loaded/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByAltText('Signature drawn by Jane Doe'),
    ).not.toBeInTheDocument();
  });
});

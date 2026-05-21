import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Proposal } from '../../types';
import { ProposalAuditCard } from './ProposalAuditCard';

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
  signer_name: 'Jane Doe',
  signer_email: 'jane@example.com',
  views: [],
} as Proposal;

describe('ProposalAuditCard', () => {
  it('renders captured signer details', () => {
    render(<ProposalAuditCard proposal={signedProposal} />);

    expect(screen.getByText('E-signature captured')).toBeInTheDocument();
    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText('jane@example.com')).toBeInTheDocument();
  });
});

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
  selected_package_snapshot: {
    package_id: 10,
    name: 'Growth',
    description: 'Selected support package.',
    currency: 'USD',
    payment_type: 'subscription',
    recurring_interval: 'month',
    recurring_interval_count: 1,
    subtotal: '2500.00',
    discount_amount: '0.00',
    tax_amount: '0.00',
    total: '2500.00',
    captured_at: '2026-05-20T18:00:00Z',
    items: [
      {
        description: 'Optimization retainer',
        quantity: '1.00',
        unit_price: '2500.00',
        discount_amount: '0.00',
        total: '2500.00',
      },
    ],
  },
  views: [],
} as Proposal;

describe('ProposalAuditCard', () => {
  it('renders selected package snapshot details', () => {
    render(<ProposalAuditCard proposal={signedProposal} />);

    expect(screen.getByText('Selected package')).toBeInTheDocument();
    expect(screen.getByText('Growth')).toBeInTheDocument();
    expect(screen.getAllByText('$2,500.00').length).toBeGreaterThan(0);
    expect(screen.getByText('Optimization retainer')).toBeInTheDocument();
    expect(screen.queryByText(/Tax included/i)).not.toBeInTheDocument();
  });
});

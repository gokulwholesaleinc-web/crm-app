import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ReactElement } from 'react';
import type { Proposal } from '../../types';
import { ProposalPackagesCard } from './ProposalDetail';
import { getPackageFormValidationError } from './proposalPackageFormValidation';

function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      {ui}
    </QueryClientProvider>,
  );
}

const proposalWithPackages = {
  id: 1,
  proposal_number: 'PROP-001',
  title: 'Package proposal',
  status: 'sent',
  view_count: 0,
  payment_type: 'one_time',
  currency: 'USD',
  created_at: '2026-05-20T00:00:00Z',
  updated_at: '2026-05-20T00:00:00Z',
  packages: [
    {
      id: 10,
      proposal_id: 1,
      name: 'Growth',
      description: 'Monthly growth support.',
      currency: 'USD',
      payment_type: 'subscription',
      recurring_interval: 'month',
      recurring_interval_count: 1,
      subtotal: '2500.00',
      discount_amount: '0.00',
      tax_amount: '0.00',
      total: '2500.00',
      sort_order: 0,
      is_recommended: true,
      is_active: true,
      items: [
        {
          id: 100,
          package_id: 10,
          description: 'Optimization retainer',
          quantity: '1.00',
          unit_price: '2500.00',
          discount_amount: '0.00',
          total: '2500.00',
          sort_order: 0,
        },
      ],
    },
  ],
} as Proposal;

describe('ProposalPackagesCard', () => {
  it('renders package details without draft controls after send', () => {
    renderWithQuery(
      <ProposalPackagesCard proposal={proposalWithPackages} isDraft={false} />,
    );

    expect(screen.getByText('Growth')).toBeInTheDocument();
    expect(screen.getAllByText('$2,500.00').length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Package options are read-only after the proposal is sent/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add package/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Deactivate/i })).not.toBeInTheDocument();
  });

  it('shows draft-only package management controls', () => {
    renderWithQuery(
      <ProposalPackagesCard
        proposal={{ ...proposalWithPackages, status: 'draft' } as Proposal}
        isDraft
      />,
    );

    expect(screen.getByRole('button', { name: /Add package/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Edit$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Deactivate/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Remove/i })).not.toBeInTheDocument();
  });

  it('blocks active zero-total packages before submitting to the API', () => {
    expect(
      getPackageFormValidationError({
        name: 'Starter',
        description: '',
        currency: 'USD',
        payment_type: 'one_time',
        recurring_interval: 'month',
        recurring_interval_count: 1,
        is_recommended: false,
        is_active: true,
        sort_order: 0,
        items: [
          {
            description: 'Implementation',
            quantity: '1.00',
            unit_price: '0.00',
            discount_amount: '0.00',
            sort_order: 0,
          },
        ],
      }),
    ).toBe('Active package total must be greater than 0');
  });
});

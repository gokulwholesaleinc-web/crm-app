import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ContractAuditCard } from './ContractAuditCard';
import type { Contract } from '../../types';

const base: Contract = {
  id: 1,
  title: 'Test Contract',
  status: 'draft',
  currency: 'USD',
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
};

describe('ContractAuditCard', () => {
  it('shows "not yet signed" when contract is unsigned', () => {
    render(<ContractAuditCard contract={base} />);
    expect(screen.getByText(/not yet signed/i)).toBeInTheDocument();
  });

  it('shows e-signature section when contract is signed', () => {
    const signed: Contract = {
      ...base,
      status: 'signed',
      signed_at: '2026-05-10T14:30:00Z',
      signed_by_name: 'Jane Doe',
    };
    render(<ContractAuditCard contract={signed} />);
    expect(screen.getByText(/e-signature captured/i)).toBeInTheDocument();
    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
  });

  it('renders signed_at timestamp when signed', () => {
    const signed: Contract = {
      ...base,
      status: 'signed',
      signed_at: '2026-05-10T14:30:00Z',
    };
    render(<ContractAuditCard contract={signed} />);
    expect(screen.getByText(/signed at/i)).toBeInTheDocument();
  });

  it('does not render signer name section when signed_by_name is absent', () => {
    const signed: Contract = {
      ...base,
      status: 'signed',
      signed_at: '2026-05-10T14:30:00Z',
    };
    render(<ContractAuditCard contract={signed} />);
    expect(screen.queryByText(/^Name$/i)).not.toBeInTheDocument();
  });
});

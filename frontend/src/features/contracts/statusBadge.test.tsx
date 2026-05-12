import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ContractStatusBadge } from './statusBadge';

describe('ContractStatusBadge', () => {
  it('renders default md size with status text', () => {
    render(<ContractStatusBadge status="draft" />);
    expect(screen.getByText('draft')).toBeInTheDocument();
  });

  it('renders sm size without visual change to text content', () => {
    render(<ContractStatusBadge status="signed" size="sm" />);
    expect(screen.getByText('signed')).toBeInTheDocument();
  });

  it('does not render dot by default', () => {
    const { container } = render(<ContractStatusBadge status="active" />);
    expect(container.querySelector('[aria-hidden]')).not.toBeInTheDocument();
  });

  it('renders dot when showDot is true', () => {
    const { container } = render(<ContractStatusBadge status="active" showDot />);
    const dot = container.querySelector('[aria-hidden="true"]');
    expect(dot).toBeInTheDocument();
    expect(dot?.className).toContain('rounded-full');
  });

  it('applies correct color classes for known statuses', () => {
    const { container: draftContainer } = render(<ContractStatusBadge status="draft" />);
    expect(draftContainer.firstChild).toHaveClass('bg-gray-100');

    const { container: activeContainer } = render(<ContractStatusBadge status="active" />);
    expect(activeContainer.firstChild).toHaveClass('bg-green-100');

    const { container: signedContainer } = render(<ContractStatusBadge status="signed" />);
    expect(signedContainer.firstChild).toHaveClass('bg-purple-100');
  });

  it('falls back to gray for unknown status', () => {
    const { container } = render(<ContractStatusBadge status="unknown-xyz" />);
    expect(container.firstChild).toHaveClass('bg-gray-100');
  });

  it('renders both sm+showDot together correctly', () => {
    const { container } = render(<ContractStatusBadge status="sent" size="sm" showDot />);
    expect(screen.getByText('sent')).toBeInTheDocument();
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  });
});

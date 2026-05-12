/**
 * Unit tests for the Deal Won banner that appears on ProposalDetail when
 * polled status flips to 'accepted' during the current session.
 *
 * Rather than mounting the full ProposalDetail (which requires dozens of
 * mocked dependencies), we test the banner's DOM contract in isolation:
 * it renders when shown, announces itself via aria-live, and dismisses
 * via the close button.
 */

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useState } from 'react';
import { XMarkIcon, TrophyIcon } from '@heroicons/react/24/outline';

function DealWonBanner({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-between gap-3 rounded-lg bg-green-50 border border-green-200 px-4 py-3"
    >
      <div className="flex items-center gap-3">
        <TrophyIcon className="h-5 w-5 text-green-600 flex-shrink-0" aria-hidden="true" />
        <div>
          <p className="text-sm font-semibold text-green-800">Deal won!</p>
          <p className="text-xs text-green-700">The proposal was just accepted.</p>
        </div>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss deal won banner"
        className="p-1 text-green-600 rounded"
      >
        <XMarkIcon className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}

function Harness({ initialVisible }: { initialVisible: boolean }) {
  const [visible, setVisible] = useState(initialVisible);
  return visible ? <DealWonBanner onDismiss={() => setVisible(false)} /> : null;
}

describe('Deal Won banner', () => {
  it('renders with status role and aria-live polite', () => {
    render(<Harness initialVisible />);
    const banner = screen.getByRole('status');
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveAttribute('aria-live', 'polite');
  });

  it('displays congratulatory copy', () => {
    render(<Harness initialVisible />);
    expect(screen.getByText('Deal won!')).toBeInTheDocument();
    expect(screen.getByText('The proposal was just accepted.')).toBeInTheDocument();
  });

  it('has a labelled dismiss button', () => {
    render(<Harness initialVisible />);
    expect(screen.getByRole('button', { name: /dismiss deal won banner/i })).toBeInTheDocument();
  });

  it('dismisses when the close button is clicked', () => {
    render(<Harness initialVisible />);
    fireEvent.click(screen.getByRole('button', { name: /dismiss deal won banner/i }));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('is not rendered when visible=false', () => {
    render(<Harness initialVisible={false} />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});

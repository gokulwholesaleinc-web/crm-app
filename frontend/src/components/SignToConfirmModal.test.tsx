import { forwardRef, useImperativeHandle } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SignToConfirmModal } from './SignToConfirmModal';

vi.mock('./SignatureCanvas', () => ({
  SignatureCanvas: forwardRef(function MockSignatureCanvas(
    {
      onSignatureChange,
    }: {
      onSignatureChange: (empty: boolean) => void;
    },
    ref,
  ) {
    useImperativeHandle(ref, () => ({
      clear: vi.fn(),
      toDataURL: () => 'data:image/png;base64,signature',
    }));
    return (
      <button type="button" onClick={() => onSignatureChange(false)}>
        Draw signature
      </button>
    );
  }),
}));

describe('SignToConfirmModal', () => {
  it('renders the selected package summary and submits its id', async () => {
    const onSubmit = vi.fn().mockResolvedValue(null);

    render(
      <SignToConfirmModal
        isOpen
        onClose={vi.fn()}
        recipientEmail="jane@example.com"
        termsAndConditions="Standard terms."
        hasMasterContract={false}
        selectedPackageId={42}
        selectedPackageSummary={{
          name: 'Growth Package',
          total: '$2,500.00',
          cadence: 'Every month',
        }}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByText('Selected package')).toBeInTheDocument();
    expect(screen.getByText('Growth Package')).toBeInTheDocument();
    expect(screen.getByText('$2,500.00')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Draw signature/i }));
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /Submit Signature/i }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          email: 'jane@example.com',
          agreedToTerms: true,
          selectedPackageId: 42,
        }),
      ),
    );
  });
});

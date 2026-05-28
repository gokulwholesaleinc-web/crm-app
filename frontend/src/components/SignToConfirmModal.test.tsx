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
  it('submits signer email, consent, and signature', async () => {
    const onSubmit = vi.fn().mockResolvedValue(null);

    render(
      <SignToConfirmModal
        isOpen
        onClose={vi.fn()}
        recipientEmail="jane@example.com"
        termsAndConditions="Standard terms."
        hasSigningDocuments={false}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Draw signature/i }));
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /Submit Signature/i }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          email: 'jane@example.com',
          agreedToTerms: true,
        }),
      ),
    );
  });

  it('only mentions countersigned PDFs when signing documents exist', async () => {
    const { rerender } = render(
      <SignToConfirmModal
        isOpen
        onClose={vi.fn()}
        recipientEmail="jane@example.com"
        termsAndConditions={null}
        hasSigningDocuments={false}
        onSubmit={vi.fn()}
      />,
    );

    await waitFor(() =>
      expect(screen.queryByText(/countersigned pdf/i)).not.toBeInTheDocument(),
    );

    rerender(
      <SignToConfirmModal
        isOpen
        onClose={vi.fn()}
        recipientEmail="jane@example.com"
        termsAndConditions={null}
        hasSigningDocuments
        signingDocumentCount={2}
        onSubmit={vi.fn()}
      />,
    );

    await waitFor(() =>
      expect(screen.getByText(/Countersigned PDFs will be emailed/i)).toBeInTheDocument(),
    );
  });
});

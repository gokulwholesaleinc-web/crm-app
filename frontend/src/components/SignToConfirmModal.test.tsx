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
  it('submits signer email and signature once a signature is drawn', async () => {
    const onSubmit = vi.fn().mockResolvedValue(null);

    render(
      <SignToConfirmModal
        isOpen
        onClose={vi.fn()}
        recipientEmail="jane@example.com"
        hasSigningDocuments={false}
        onSubmit={onSubmit}
      />,
    );

    // No redundant Terms & Conditions card or agree-to-terms checkbox is
    // rendered — the binding terms live in the proposal document itself.
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(
      screen.queryByText(/agree to the terms and conditions/i),
    ).not.toBeInTheDocument();

    // Signature alone enables the Submit button.
    const submit = screen.getByRole('button', { name: /Submit Signature/i });
    expect(submit).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: /Draw signature/i }));
    expect(submit).not.toBeDisabled();

    fireEvent.click(submit);

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          email: 'jane@example.com',
          signatureDataUrl: 'data:image/png;base64,signature',
        }),
      ),
    );
    // No agreed-to-terms flag is captured by the modal anymore.
    expect(onSubmit.mock.calls[0][0]).not.toHaveProperty('agreedToTerms');
  });

  it('keeps the ESIGN electronic-signature consent line', async () => {
    render(
      <SignToConfirmModal
        isOpen
        onClose={vi.fn()}
        recipientEmail="jane@example.com"
        hasSigningDocuments={false}
        onSubmit={vi.fn()}
      />,
    );

    expect(
      screen.getByText(/consent to use an electronic signature/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /View full e-sign consent/i }),
    ).toBeInTheDocument();
  });

  it('only mentions countersigned PDFs when signing documents exist', async () => {
    const { rerender } = render(
      <SignToConfirmModal
        isOpen
        onClose={vi.fn()}
        recipientEmail="jane@example.com"
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

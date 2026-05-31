import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { CheckIcon, PencilIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { SignatureCanvas, type SignatureCanvasHandle } from './SignatureCanvas';

// Brand gold; the spec calls this out explicitly ("NOT teal"). Used
// for accent surfaces inside the modal so the e-sign experience
// matches Link Creative's identity instead of the generic teal of
// the reference screenshot.
const ACCENT_GOLD = '#D4A574';

export interface SignToConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Pre-filled (and locked) email — must match the proposal recipient. */
  recipientEmail: string;
  /** When true, signing creates one or more countersigned PDFs after submission. */
  hasSigningDocuments: boolean;
  signingDocumentCount?: number;
  /**
   * Returns `null` on success, or an error message string to display
   * inline. The modal handles all submit-disabled / pending state.
   */
  onSubmit: (payload: {
    signatureDataUrl: string;
    email: string;
  }) => Promise<string | null>;
}

export function SignToConfirmModal({
  isOpen,
  onClose,
  recipientEmail,
  hasSigningDocuments,
  signingDocumentCount = 0,
  onSubmit,
}: SignToConfirmModalProps) {
  const sigRef = useRef<SignatureCanvasHandle | null>(null);
  const [hasSignature, setHasSignature] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset every time the modal opens so a reopen doesn't carry over
  // a stale signature.
  useEffect(() => {
    if (!isOpen) return;
    setHasSignature(false);
    setSubmitting(false);
    setError(null);
    sigRef.current?.clear();
  }, [isOpen]);

  const today = useMemo(
    () =>
      new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      }).format(new Date()),
    [],
  );

  // Build the consent-anchor URL explicitly so it always carries the
  // proposal's token (the modal lives on `/proposals/public/:token`)
  // and survives any future modal reuse outside that route.
  const consentHref = useMemo(() => {
    if (typeof window === 'undefined') return '#esign-consent';
    return `${window.location.pathname}${window.location.search}#esign-consent`;
  }, []);

  const canSubmit = hasSignature && !submitting;

  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return;
    const dataUrl = sigRef.current?.toDataURL() ?? null;
    if (!dataUrl) {
      setError('Please draw your signature before submitting.');
      return;
    }
    setSubmitting(true);
    setError(null);
    const message = await onSubmit({
      signatureDataUrl: dataUrl,
      email: recipientEmail,
    });
    if (message) {
      setError(message);
      setSubmitting(false);
      return;
    }
    setSubmitting(false);
  }, [canSubmit, onSubmit, recipientEmail]);

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog
        as="div"
        className="relative z-50"
        onClose={submitting ? () => {} : onClose}
      >
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto overscroll-contain">
          <div className="flex min-h-full items-center justify-center p-4 sm:p-6">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel
                className="w-full max-w-md transform overflow-hidden rounded-3xl bg-neutral-950/95 ring-1 ring-white/10 shadow-2xl backdrop-blur-md px-6 pt-6 pb-6 text-left align-middle text-white"
              >
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <Dialog.Title
                      as="h2"
                      className="font-serif text-2xl leading-tight tracking-tight text-white"
                    >
                      Sign to Confirm
                    </Dialog.Title>
                    <p className="mt-1 text-sm text-white/60">
                      Draw your signature in the box below
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={onClose}
                    disabled={submitting}
                    className="rounded-md p-1.5 text-white/60 hover:text-white hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/50 disabled:opacity-50"
                    aria-label="Close signing dialog"
                  >
                    <XMarkIcon className="h-5 w-5" aria-hidden="true" />
                  </button>
                </div>

                <div className="space-y-1.5">
                  <label
                    htmlFor="sign-to-confirm-email"
                    className="block text-[10px] font-mono uppercase tracking-[0.18em] text-white/50"
                  >
                    Email address
                  </label>
                  <input
                    id="sign-to-confirm-email"
                    type="email"
                    value={recipientEmail}
                    readOnly
                    autoComplete="email"
                    inputMode="email"
                    spellCheck={false}
                    className="block w-full rounded-2xl bg-white/5 ring-1 ring-white/10 px-4 py-2.5 text-sm text-white/90 placeholder-white/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40"
                    aria-readonly="true"
                  />
                </div>

                <div className="mt-4">
                  <SignatureCanvas
                    ref={sigRef}
                    accentHex={ACCENT_GOLD}
                    onSignatureChange={(empty) => setHasSignature(!empty)}
                    disabled={submitting}
                  />
                  <div className="mt-2 flex items-center justify-between text-xs text-white/50">
                    <span className="font-mono tracking-wide">{today}</span>
                    <button
                      type="button"
                      onClick={() => sigRef.current?.clear()}
                      disabled={submitting || !hasSignature}
                      className="text-white/70 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/40 disabled:opacity-40 disabled:hover:text-white/70"
                    >
                      Clear
                    </button>
                  </div>
                </div>

                {error && (
                  <p
                    role="alert"
                    aria-live="polite"
                    className="mt-4 rounded-2xl bg-red-500/10 ring-1 ring-red-400/30 px-4 py-2.5 text-sm text-red-200"
                  >
                    {error}
                  </p>
                )}

                <p className="mt-5 text-xs leading-relaxed text-white/70">
                  By submitting, you consent to use an electronic signature under
                  the US ESIGN Act and applicable state UETA statutes.{' '}
                  <a
                    href={consentHref}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline decoration-white/40 underline-offset-2 hover:decoration-white/80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/50 rounded-sm"
                    style={{ color: ACCENT_GOLD }}
                  >
                    View full e-sign consent
                  </a>
                  .
                </p>

                <div className="mt-3 flex flex-col-reverse sm:flex-row items-stretch sm:items-center gap-2">
                  <button
                    type="button"
                    onClick={onClose}
                    disabled={submitting}
                    className="inline-flex items-center justify-center gap-1.5 rounded-2xl px-5 py-2.5 text-sm font-medium text-white/90 bg-white/5 ring-1 ring-white/15 hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleSubmit}
                    disabled={!canSubmit}
                    className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl px-5 py-2.5 text-sm font-semibold text-neutral-900 shadow-sm hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/60 disabled:cursor-not-allowed disabled:opacity-50 transition-[filter,opacity]"
                    style={{ backgroundColor: ACCENT_GOLD, outlineColor: ACCENT_GOLD }}
                    aria-disabled={!canSubmit}
                  >
                    {submitting ? (
                      <span className="inline-flex items-center gap-2">
                        <CheckIcon className="h-4 w-4" aria-hidden="true" />
                        Submitting…
                      </span>
                    ) : (
                      <>
                        <PencilIcon className="h-4 w-4" aria-hidden="true" />
                        Submit Signature
                      </>
                    )}
                  </button>
                </div>
                {hasSigningDocuments && !submitting && (
                  <p className="mt-3 text-center text-[11px] text-white/40">
                    {signingDocumentCount > 1
                      ? 'Countersigned PDFs will be emailed to you after you submit.'
                      : 'A countersigned PDF will be emailed to you after you submit.'}
                  </p>
                )}
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

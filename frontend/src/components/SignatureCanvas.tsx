import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import ReactSignatureCanvas from 'react-signature-canvas';

export interface SignatureCanvasHandle {
  /** Returns the drawn signature as a base64 PNG data-URL, or null when empty. */
  toDataURL(): string | null;
  /** Wipes the canvas. */
  clear(): void;
  /** True while nothing has been drawn yet. */
  isEmpty(): boolean;
}

export interface SignatureCanvasProps {
  /** Brand accent applied to the underline + "Sign here" placeholder ring. */
  accentHex?: string;
  /** Fires whenever the empty/not-empty state flips so the parent can
   *  enable Submit. Does not fire on every stroke. */
  onSignatureChange?: (isEmpty: boolean) => void;
  /** Disables drawing (e.g. while the parent is submitting). */
  disabled?: boolean;
}

/**
 * Drawn-signature surface. Wraps `react-signature-canvas` and resizes
 * the underlying HTMLCanvasElement to match its CSS container so the
 * stroke registers at the cursor — react-signature-canvas otherwise
 * draws at the default 300x150 internal resolution regardless of CSS.
 */
export const SignatureCanvas = forwardRef<SignatureCanvasHandle, SignatureCanvasProps>(
  function SignatureCanvas({ accentHex = '#D4A574', onSignatureChange, disabled }, ref) {
    const sigRef = useRef<ReactSignatureCanvas | null>(null);
    const wrapperRef = useRef<HTMLDivElement | null>(null);
    const [isEmpty, setIsEmpty] = useState(true);

    useImperativeHandle(
      ref,
      () => ({
        toDataURL: () => {
          const sig = sigRef.current;
          if (!sig || sig.isEmpty()) return null;
          // Trim to the bounding box of the actual strokes so the
          // stamped image isn't dominated by transparent padding.
          return sig.getTrimmedCanvas().toDataURL('image/png');
        },
        clear: () => {
          sigRef.current?.clear();
          if (!isEmpty) {
            setIsEmpty(true);
            onSignatureChange?.(true);
          }
        },
        isEmpty: () => sigRef.current?.isEmpty() ?? true,
      }),
      [isEmpty, onSignatureChange],
    );

    // Resize the canvas's internal pixel buffer to match the rendered
    // CSS size (HiDPI-aware). Without this the cursor offset drifts
    // because the canvas internal size != CSS size.
    useEffect(() => {
      const sig = sigRef.current;
      const wrapper = wrapperRef.current;
      if (!sig || !wrapper) return;
      const canvas = sig.getCanvas();
      const ratio = Math.max(window.devicePixelRatio || 1, 1);
      const rect = wrapper.getBoundingClientRect();
      canvas.width = rect.width * ratio;
      canvas.height = rect.height * ratio;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      const ctx = canvas.getContext('2d');
      ctx?.scale(ratio, ratio);
      sig.clear();
    }, []);

    const handleEnd = () => {
      const sig = sigRef.current;
      if (!sig) return;
      const empty = sig.isEmpty();
      if (empty !== isEmpty) {
        setIsEmpty(empty);
        onSignatureChange?.(empty);
      }
    };

    return (
      <div
        ref={wrapperRef}
        className="relative w-full h-40 rounded-2xl border border-white/15 bg-white/5"
      >
        <ReactSignatureCanvas
          ref={sigRef}
          penColor="#ffffff"
          velocityFilterWeight={0.7}
          minWidth={1.2}
          maxWidth={2.6}
          throttle={16}
          clearOnResize={false}
          onEnd={handleEnd}
          canvasProps={{
            className: `block w-full h-full rounded-2xl ${disabled ? 'pointer-events-none opacity-60' : 'cursor-crosshair'}`,
            'aria-label': 'Signature pad — draw your signature with mouse or touch',
            role: 'img',
          }}
        />
        {isEmpty && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-white/40 font-serif italic"
          >
            Sign here
          </div>
        )}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute left-6 right-6 bottom-6 h-px"
          style={{ backgroundColor: accentHex + '40' }}
        />
      </div>
    );
  },
);

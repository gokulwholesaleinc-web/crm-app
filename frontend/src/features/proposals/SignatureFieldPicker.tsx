import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist';
import type { PDFDocumentProxy } from 'pdfjs-dist';
// pdf.js v4 ships an .mjs worker. Vite's ``?url`` suffix asset-pipelines
// it next to the bundle so the worker URL stays version-locked to the
// installed pdfjs-dist — no CDN, no manual public/ copy.
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { Modal, ModalFooter, Button } from '../../components/ui';
import type { SignatureFieldCoords } from '../../types';

GlobalWorkerOptions.workerSrc = pdfWorker;

const RENDER_SCALE = 1.5;

interface SignatureFieldPickerProps {
  isOpen: boolean;
  onClose: () => void;
  /** Object URL or remote URL pointing at the master contract PDF bytes. */
  masterPdfUrl: string;
  currentCoords: SignatureFieldCoords | null;
  onSave: (coords: SignatureFieldCoords) => Promise<void>;
}

interface DrawnBox {
  /** Page index in pdf.js space (0-indexed). */
  pageIdx: number;
  /** Screen-pixel box relative to the rendered canvas. */
  leftPx: number;
  topPx: number;
  widthPx: number;
  heightPx: number;
}

function clamp(value: number, min: number, max: number): number {
  if (value < min) return min;
  if (value > max) return max;
  return value;
}

/**
 * Convert a screen-pixel box on a pdf.js-rendered canvas to PDF points.
 *
 * pdf.js renders top-down; PDF points are bottom-up, so the y axis
 * flips and the saved ``y`` is the **bottom** edge of the box. The
 * canvas was rendered at ``RENDER_SCALE``, so dividing through gives
 * us back PDF points (1 pt = 1/72 in).
 */
function boxToPdfCoords(
  box: DrawnBox,
  canvasHeightPx: number,
): { x: number; y: number; w: number; h: number } {
  const x = box.leftPx / RENDER_SCALE;
  const w = box.widthPx / RENDER_SCALE;
  const h = box.heightPx / RENDER_SCALE;
  const bottomPx = box.topPx + box.heightPx;
  const y = (canvasHeightPx - bottomPx) / RENDER_SCALE;
  return { x, y, w, h };
}

/** Inverse of ``boxToPdfCoords``. Pre-fills the canvas with the saved box. */
function pdfCoordsToBox(
  coords: SignatureFieldCoords,
  canvasHeightPx: number,
): DrawnBox {
  const widthPx = coords.w * RENDER_SCALE;
  const heightPx = coords.h * RENDER_SCALE;
  const leftPx = coords.x * RENDER_SCALE;
  const bottomPx = canvasHeightPx - coords.y * RENDER_SCALE;
  const topPx = bottomPx - heightPx;
  return {
    pageIdx: coords.page - 1,
    leftPx,
    topPx,
    widthPx,
    heightPx,
  };
}

export function SignatureFieldPicker({
  isOpen,
  onClose,
  masterPdfUrl,
  currentCoords,
  onSave,
}: SignatureFieldPickerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const docRef = useRef<PDFDocumentProxy | null>(null);
  const dragOriginRef = useRef<{ x: number; y: number } | null>(null);
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);

  const [pageCount, setPageCount] = useState(0);
  const [pageIdx, setPageIdx] = useState(0);
  const [canvasSize, setCanvasSize] = useState<{ w: number; h: number } | null>(null);
  const [box, setBox] = useState<DrawnBox | null>(null);
  const [isLoadingDoc, setIsLoadingDoc] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // (Re)load the document each time the modal opens with a fresh URL.
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setIsLoadingDoc(true);
    setDocError(null);
    setBox(null);
    setCanvasSize(null);

    const loadingTask = getDocument(masterPdfUrl);
    loadingTask.promise
      .then((doc) => {
        if (cancelled) {
          void doc.destroy();
          return;
        }
        docRef.current = doc;
        setPageCount(doc.numPages);
        const initialIdx = currentCoords
          ? clamp(currentCoords.page - 1, 0, doc.numPages - 1)
          : 0;
        setPageIdx(initialIdx);
        setIsLoadingDoc(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setIsLoadingDoc(false);
        setDocError(
          err instanceof Error
            ? err.message
            : 'Failed to load master contract PDF',
        );
      });

    return () => {
      cancelled = true;
      void loadingTask.destroy();
      if (docRef.current) {
        void docRef.current.destroy();
        docRef.current = null;
      }
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel();
        renderTaskRef.current = null;
      }
    };
  }, [isOpen, masterPdfUrl, currentCoords]);

  // Render the active page to the canvas.
  useEffect(() => {
    const doc = docRef.current;
    const canvas = canvasRef.current;
    if (!doc || !canvas || isLoadingDoc) return;

    let cancelled = false;
    void (async () => {
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel();
        renderTaskRef.current = null;
      }
      const page = await doc.getPage(pageIdx + 1);
      if (cancelled) return;
      const viewport = page.getViewport({ scale: RENDER_SCALE });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      const task = page.render({ canvasContext: ctx, viewport });
      renderTaskRef.current = task;
      try {
        await task.promise;
      } catch {
        // pdf.js throws ``RenderingCancelledException`` when we
        // cancel an in-flight render to draw a different page.
        // That's expected — don't surface it.
        return;
      }
      if (cancelled) return;
      setCanvasSize({ w: viewport.width, h: viewport.height });

      // Pre-fill the saved box only when we land on its page.
      if (currentCoords && currentCoords.page - 1 === pageIdx) {
        setBox(pdfCoordsToBox(currentCoords, viewport.height));
      } else {
        setBox(null);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pageIdx, isLoadingDoc, currentCoords]);

  // --- Drag handlers ----------------------------------------------

  const localPoint = useCallback((e: React.PointerEvent) => {
    const el = overlayRef.current;
    if (!el) return { x: 0, y: 0 };
    const rect = el.getBoundingClientRect();
    return {
      x: clamp(e.clientX - rect.left, 0, rect.width),
      y: clamp(e.clientY - rect.top, 0, rect.height),
    };
  }, []);

  const handlePointerDown = (e: React.PointerEvent) => {
    if (!canvasSize) return;
    overlayRef.current?.setPointerCapture(e.pointerId);
    const p = localPoint(e);
    dragOriginRef.current = p;
    setBox({
      pageIdx,
      leftPx: p.x,
      topPx: p.y,
      widthPx: 0,
      heightPx: 0,
    });
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    const origin = dragOriginRef.current;
    if (!origin || !canvasSize) return;
    const p = localPoint(e);
    const leftPx = Math.min(origin.x, p.x);
    const topPx = Math.min(origin.y, p.y);
    const widthPx = Math.abs(p.x - origin.x);
    const heightPx = Math.abs(p.y - origin.y);
    setBox({ pageIdx, leftPx, topPx, widthPx, heightPx });
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    overlayRef.current?.releasePointerCapture(e.pointerId);
    dragOriginRef.current = null;
  };

  // --- Save / cancel ----------------------------------------------

  const canSave =
    !!box && !!canvasSize && box.widthPx > 4 && box.heightPx > 4 && !saving;

  const handleSave = async () => {
    if (!box || !canvasSize) return;
    setSaving(true);
    try {
      const pdfBox = boxToPdfCoords(box, canvasSize.h);
      await onSave({
        page: box.pageIdx + 1,
        ...pdfBox,
      });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const goPrev = () => setPageIdx((i) => Math.max(0, i - 1));
  const goNext = () => setPageIdx((i) => Math.min(pageCount - 1, i + 1));

  return (
    <Modal
      isOpen={isOpen}
      onClose={saving ? () => {} : onClose}
      title="Place signature box"
      description="Click and drag on the page to outline where the signer's signature should land."
      size="full"
      closeOnOverlayClick={!saving}
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={goPrev}
              disabled={pageIdx === 0 || isLoadingDoc}
              aria-label="Previous page"
            >
              <ArrowLeftIcon className="h-4 w-4" aria-hidden="true" />
            </Button>
            <span
              className="text-sm text-gray-700 dark:text-gray-200"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              Page {pageCount === 0 ? 0 : pageIdx + 1} of {pageCount}
            </span>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={goNext}
              disabled={pageIdx >= pageCount - 1 || isLoadingDoc}
              aria-label="Next page"
            >
              <ArrowRightIcon className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
          {!currentCoords && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              No box placed — signature will land in the auto-box (bottom of last page).
            </p>
          )}
          {currentCoords && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Saved on page {currentCoords.page}.
            </p>
          )}
        </div>

        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/40 p-3 overflow-auto max-h-[70vh]">
          {isLoadingDoc && (
            <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 p-6">
              <ArrowPathIcon className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              Loading master contract…
            </div>
          )}
          {docError && (
            <p
              role="alert"
              aria-live="polite"
              className="text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded px-3 py-2"
            >
              {docError}
            </p>
          )}
          {!isLoadingDoc && !docError && (
            <div className="relative inline-block">
              <canvas
                ref={canvasRef}
                aria-label="Master contract page — click and drag to draw a signature box"
                className="block bg-white shadow-sm"
              />
              <div
                ref={overlayRef}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerCancel={handlePointerUp}
                className="absolute inset-0 cursor-crosshair touch-none"
                style={{ touchAction: 'none' }}
              >
                {box && box.pageIdx === pageIdx && (
                  <div
                    className="absolute border-2 border-primary-500 bg-primary-500/15 pointer-events-none"
                    style={{
                      left: `${box.leftPx}px`,
                      top: `${box.topPx}px`,
                      width: `${box.widthPx}px`,
                      height: `${box.heightPx}px`,
                    }}
                    aria-hidden="true"
                  />
                )}
              </div>
            </div>
          )}
        </div>

        <ModalFooter>
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            disabled={saving}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="primary"
            onClick={handleSave}
            disabled={!canSave}
            isLoading={saving}
          >
            Save placement
          </Button>
        </ModalFooter>
      </div>
    </Modal>
  );
}

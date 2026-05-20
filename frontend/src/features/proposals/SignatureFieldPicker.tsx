import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  ArrowPathIcon,
  CalendarDaysIcon,
  PencilSquareIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist';
import type { PDFDocumentProxy } from 'pdfjs-dist';
// pdf.js v4 ships an .mjs worker. Vite's ``?url`` suffix asset-pipelines
// it next to the bundle so the worker URL stays version-locked to the
// installed pdfjs-dist — no CDN, no manual public/ copy.
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { Modal, ModalFooter, Button } from '../../components/ui';
import type { SignatureFieldCoords, SignatureFieldCoordsValue } from '../../types';
import { normalizeSignaturePlacements } from './signaturePlacements';

GlobalWorkerOptions.workerSrc = pdfWorker;

const RENDER_SCALE = 1.5;

type PlacementKind = 'signature' | 'date';

export interface SignatureFieldPlacements {
  signatureFieldCoords: SignatureFieldCoords[];
  dateFieldCoords: SignatureFieldCoords[];
}

interface SignatureFieldPickerProps {
  isOpen: boolean;
  onClose: () => void;
  /** Object URL or remote URL pointing at the master contract PDF bytes. */
  masterPdfUrl: string;
  currentCoords: SignatureFieldCoordsValue | null;
  currentDateCoords: SignatureFieldCoordsValue | null;
  onSave: (placements: SignatureFieldPlacements) => Promise<void>;
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

function placementLabel(kind: PlacementKind): string {
  return kind === 'signature' ? 'Signature' : 'Date';
}

export function SignatureFieldPicker({
  isOpen,
  onClose,
  masterPdfUrl,
  currentCoords,
  currentDateCoords,
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
  const [placements, setPlacements] = useState<{
    signature: SignatureFieldCoords[];
    date: SignatureFieldCoords[];
  }>({
    signature: normalizeSignaturePlacements(currentCoords),
    date: normalizeSignaturePlacements(currentDateCoords),
  });
  const [activeKind, setActiveKind] = useState<PlacementKind>('signature');
  const [draftBox, setDraftBox] = useState<DrawnBox | null>(null);
  const [isLoadingDoc, setIsLoadingDoc] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Held in a ref (not the dep array) so the doc-load effect doesn't
  // re-fire when ``useProposal``'s 20 s polling produces fresh placement
  // objects on each refetch — a user mid-drag would otherwise watch their
  // boxes reset every poll cycle.
  const initialCoordsRef = useRef({ currentCoords, currentDateCoords });
  initialCoordsRef.current = { currentCoords, currentDateCoords };

  // (Re)load the document each time the modal opens with a fresh URL.
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setIsLoadingDoc(true);
    setDocError(null);
    setDraftBox(null);
    setCanvasSize(null);
    setPlacements({
      signature: normalizeSignaturePlacements(initialCoordsRef.current.currentCoords),
      date: normalizeSignaturePlacements(initialCoordsRef.current.currentDateCoords),
    });

    const loadingTask = getDocument(masterPdfUrl);
    loadingTask.promise
      .then((doc) => {
        if (cancelled) {
          void doc.destroy();
          return;
        }
        docRef.current = doc;
        setPageCount(doc.numPages);
        const seed =
          normalizeSignaturePlacements(initialCoordsRef.current.currentCoords)[0] ??
          normalizeSignaturePlacements(initialCoordsRef.current.currentDateCoords)[0];
        const initialIdx = seed
          ? clamp(seed.page - 1, 0, doc.numPages - 1)
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
  }, [isOpen, masterPdfUrl]);

  // Render the active page to the canvas.
  useEffect(() => {
    const doc = docRef.current;
    const canvas = canvasRef.current;
    if (!doc || !canvas || isLoadingDoc) return;

    let cancelled = false;
    void (async () => {
      try {
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
        } catch (err) {
          // pdf.js throws ``RenderingCancelledException`` when we cancel
          // an in-flight render to draw a different page. Any other error
          // must surface instead of leaving a blank canvas.
          const name = (err as { name?: string } | undefined)?.name;
          if (name === 'RenderingCancelledException') return;
          throw err;
        }
        if (cancelled) return;
        setCanvasSize({ w: viewport.width, h: viewport.height });
        setDraftBox(null);
      } catch (err) {
        if (cancelled) return;
        setDocError(
          err instanceof Error
            ? err.message
            : 'Failed to render master contract page',
        );
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pageIdx, isLoadingDoc]);

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
    setDraftBox({
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
    setDraftBox({ pageIdx, leftPx, topPx, widthPx, heightPx });
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    overlayRef.current?.releasePointerCapture(e.pointerId);
    dragOriginRef.current = null;
    if (!draftBox || !canvasSize || draftBox.widthPx <= 4 || draftBox.heightPx <= 4) {
      setDraftBox(null);
      return;
    }
    const pdfBox = boxToPdfCoords(draftBox, canvasSize.h);
    setPlacements((curr) => ({
      ...curr,
      [activeKind]: curr[activeKind].concat({
        page: draftBox.pageIdx + 1,
        ...pdfBox,
      }),
    }));
    setDraftBox(null);
  };

  // --- Save / cancel ----------------------------------------------

  const canSave = Boolean(
    placements.signature.length > 0 && placements.date.length > 0 && !saving,
  );

  const handleSave = async () => {
    if (placements.signature.length === 0 || placements.date.length === 0) return;
    setSaving(true);
    try {
      await onSave({
        signatureFieldCoords: placements.signature,
        dateFieldCoords: placements.date,
      });
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const goPrev = () => setPageIdx((i) => Math.max(0, i - 1));
  const goNext = () => setPageIdx((i) => Math.min(pageCount - 1, i + 1));

  const removePlacement = (kind: PlacementKind, index: number) => {
    setPlacements((curr) => ({
      ...curr,
      [kind]: curr[kind].filter((_, placementIndex) => placementIndex !== index),
    }));
  };

  const visibleBoxes: Array<{
    kind: PlacementKind;
    box: DrawnBox;
    index: number | null;
  }> = [];
  if (canvasSize) {
    for (const kind of ['signature', 'date'] as const) {
      placements[kind].forEach((coords, index) => {
        if (coords.page - 1 === pageIdx) {
          visibleBoxes.push({ kind, index, box: pdfCoordsToBox(coords, canvasSize.h) });
        }
      });
    }
  }
  if (draftBox && draftBox.pageIdx === pageIdx) {
    visibleBoxes.push({ kind: activeKind, index: null, box: draftBox });
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={saving ? () => {} : onClose}
      title="Place signature and date"
      description="Choose a field, then click and drag on the PDF page to outline where it should land."
      size="full"
      closeOnOverlayClick={!saving}
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
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

          <div className="flex flex-wrap items-center gap-2">
            <PlacementToggle
              kind="signature"
              activeKind={activeKind}
              count={placements.signature.length}
              onClick={setActiveKind}
            />
            <PlacementToggle
              kind="date"
              activeKind={activeKind}
              count={placements.date.length}
              onClick={setActiveKind}
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
          <span>
            Signatures {placements.signature.length > 0 ? `${placements.signature.length} placed` : 'not placed'}
          </span>
          <span>
            Dates {placements.date.length > 0 ? `${placements.date.length} placed` : 'not placed'}
          </span>
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
                aria-label="Master contract page — click and drag to draw the active field"
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
                {visibleBoxes.map(({ kind, box, index }) => {
                  const isDate = kind === 'date';
                  return (
                    <div
                      key={`${kind}-${index ?? 'draft'}-${box.leftPx}-${box.topPx}`}
                      className={`absolute pointer-events-none border-2 ${
                        isDate
                          ? 'border-emerald-500 bg-emerald-500/15'
                          : 'border-primary-500 bg-primary-500/15'
                      }`}
                      style={{
                        left: `${box.leftPx}px`,
                        top: `${box.topPx}px`,
                        width: `${box.widthPx}px`,
                        height: `${box.heightPx}px`,
                      }}
                      aria-hidden={index === null ? 'true' : undefined}
                    >
                      <span
                        className={`absolute -top-5 left-0 rounded px-1.5 py-0.5 text-[10px] font-medium text-white ${
                          isDate ? 'bg-emerald-600' : 'bg-primary-600'
                        }`}
                      >
                        {placementLabel(kind)}
                      </span>
                      {index !== null && (
                        <button
                          type="button"
                          onPointerDown={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                          }}
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                            removePlacement(kind, index);
                          }}
                          className={`pointer-events-auto absolute -right-3 -top-3 inline-flex h-6 w-6 items-center justify-center rounded-full border border-white text-white shadow-sm ${
                            isDate
                              ? 'bg-emerald-600 hover:bg-emerald-700'
                              : 'bg-primary-600 hover:bg-primary-700'
                          }`}
                          aria-label={`Remove ${placementLabel(kind).toLowerCase()} placement`}
                          title={`Remove ${placementLabel(kind).toLowerCase()} placement`}
                        >
                          <XMarkIcon className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      )}
                    </div>
                  );
                })}
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
            Save placements
          </Button>
        </ModalFooter>
      </div>
    </Modal>
  );
}

interface PlacementToggleProps {
  kind: PlacementKind;
  activeKind: PlacementKind;
  count: number;
  onClick: (kind: PlacementKind) => void;
}

function PlacementToggle({
  kind,
  activeKind,
  count,
  onClick,
}: PlacementToggleProps) {
  const isActive = kind === activeKind;
  const Icon = kind === 'signature' ? PencilSquareIcon : CalendarDaysIcon;
  const placed = count > 0;
  return (
    <button
      type="button"
      onClick={() => onClick(kind)}
      className={`inline-flex items-center gap-1.5 rounded border px-3 py-1.5 text-sm font-medium transition-colors ${
        isActive
          ? 'border-primary-500 bg-primary-50 text-primary-700 dark:border-primary-400 dark:bg-primary-950/30 dark:text-primary-300'
          : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700'
      }`}
      aria-pressed={isActive}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {placementLabel(kind)}
      <span className={placed ? 'text-green-600 dark:text-green-400' : 'text-amber-600 dark:text-amber-300'}>
        {placed ? `${count} set` : 'needed'}
      </span>
    </button>
  );
}

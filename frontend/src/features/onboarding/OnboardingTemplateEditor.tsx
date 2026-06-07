import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  ArrowPathIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist';
import type { PDFDocumentProxy } from 'pdfjs-dist';
// pdf.js v4 ships an .mjs worker. Vite's ``?url`` suffix asset-pipelines it
// next to the bundle so the worker URL stays version-locked to the installed
// pdfjs-dist — no CDN, no manual public/ copy. (Same setup as the proposals
// SignatureFieldPicker.)
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { Modal, ModalFooter, Button, Input, Select } from '../../components/ui';
import {
  RENDER_SCALE,
  boxToPdfCoords,
  pdfCoordsToBox,
  clamp,
  type DrawnBox,
} from '../../lib/pdfCoords';
import type {
  OnboardingFieldDefinition,
  OnboardingFieldKind,
  OnboardingFieldPrefill,
} from '../../types';
import { extractApiErrorDetail } from '../../utils/errors';
import {
  FIELD_KINDS,
  KIND_META,
  ESIGN_PREFILL_OPTIONS,
  fieldErrors,
  nextFieldId,
} from './fieldKinds';

GlobalWorkerOptions.workerSrc = pdfWorker;

/**
 * In-editor field. ``id`` is a freely-editable, persisted property, so it
 * can't key selection or React lists (editing it would orphan the
 * selection — finding #5). ``_key`` is a stable internal handle assigned on
 * add; it is STRIPPED before the field list is emitted to the parent.
 */
interface EditorField extends OnboardingFieldDefinition {
  _key: string;
}

/** Monotonic counter for stable internal field keys (per module load). */
let _keySeq = 0;
function nextKey(): string {
  _keySeq += 1;
  return `f${_keySeq}`;
}

/** Attach a stable internal key to each incoming persisted field. */
function withKeys(fields: OnboardingFieldDefinition[]): EditorField[] {
  return fields.map((f) => ({ ...f, _key: nextKey() }));
}

/** Drop the internal ``_key`` so the persisted shape stays clean. */
function stripKeys(fields: EditorField[]): OnboardingFieldDefinition[] {
  return fields.map(({ _key, ...field }) => field);
}

// ===========================================================================
// Controlled body — the canvas + overlay + per-field panel, with NO Modal.
// Hosted by the Modal editor (editing an existing template) AND inline by the
// "Create template" wizard (authoring against a local object-URL preview).
// Source of truth for editing (keys, selection); emits the stripped field list
// up via ``onChange`` and re-seeds from ``value`` only when ``pdfUrl`` changes.
// ===========================================================================

interface OnboardingTemplateEditorBodyProps {
  /** Object URL or remote URL pointing at the template PDF bytes. */
  pdfUrl: string;
  /** The current field list (controlled). */
  value: OnboardingFieldDefinition[];
  /** Emits the field list (without internal keys) on every edit. */
  onChange: (fields: OnboardingFieldDefinition[]) => void;
}

export function OnboardingTemplateEditorBody({
  pdfUrl,
  value,
  onChange,
}: OnboardingTemplateEditorBodyProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const docRef = useRef<PDFDocumentProxy | null>(null);
  const dragOriginRef = useRef<{ x: number; y: number } | null>(null);
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);

  const [pageCount, setPageCount] = useState(0);
  const [pageIdx, setPageIdx] = useState(0);
  const [canvasSize, setCanvasSize] = useState<{ w: number; h: number } | null>(null);
  const [fields, setFields] = useState<EditorField[]>(() => withKeys(value));
  const [activeKind, setActiveKind] = useState<OnboardingFieldKind>('signature');
  // Selection is keyed on the stable internal ``_key``, never the editable
  // ``id`` — editing an id must not orphan the selection (finding #5).
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [draftBox, setDraftBox] = useState<DrawnBox | null>(null);
  const [isLoadingDoc, setIsLoadingDoc] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);

  // Held in a ref so the doc-load effect re-seeds from the freshest value on a
  // pdfUrl change without re-firing when the parent re-renders with the same URL.
  const initialValueRef = useRef(value);
  initialValueRef.current = value;

  // Emit field changes up to the parent (stripped of the internal ``_key``).
  // The parent's value tracks these emissions; the doc-load effect below only
  // re-seeds on a pdfUrl change, so this never loops.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  useEffect(() => {
    onChangeRef.current(stripKeys(fields));
  }, [fields]);

  // (Re)load the document whenever the source URL changes; re-seed from value.
  useEffect(() => {
    let cancelled = false;
    setIsLoadingDoc(true);
    setDocError(null);
    setDraftBox(null);
    setSelectedKey(null);
    setCanvasSize(null);
    setFields(withKeys(initialValueRef.current));

    const loadingTask = getDocument(pdfUrl);
    loadingTask.promise
      .then((doc) => {
        if (cancelled) {
          void doc.destroy();
          return;
        }
        docRef.current = doc;
        setPageCount(doc.numPages);
        const seed = initialValueRef.current[0];
        setPageIdx(seed ? clamp(seed.page - 1, 0, doc.numPages - 1) : 0);
        setIsLoadingDoc(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setIsLoadingDoc(false);
        setDocError(extractApiErrorDetail(err) ?? 'Failed to load template PDF');
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
  }, [pdfUrl]);

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
          // pdf.js throws ``RenderingCancelledException`` when we cancel an
          // in-flight render to draw a different page. Any other error must
          // surface instead of leaving a blank canvas.
          const name = (err as { name?: string } | undefined)?.name;
          if (name === 'RenderingCancelledException') return;
          throw err;
        }
        if (cancelled) return;
        setCanvasSize({ w: viewport.width, h: viewport.height });
        setDraftBox(null);
      } catch (err) {
        if (cancelled) return;
        setDocError(extractApiErrorDetail(err) ?? 'Failed to render template page');
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
    setDraftBox({ pageIdx, leftPx: p.x, topPx: p.y, widthPx: 0, heightPx: 0 });
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    const origin = dragOriginRef.current;
    if (!origin || !canvasSize) return;
    const p = localPoint(e);
    setDraftBox({
      pageIdx,
      leftPx: Math.min(origin.x, p.x),
      topPx: Math.min(origin.y, p.y),
      widthPx: Math.abs(p.x - origin.x),
      heightPx: Math.abs(p.y - origin.y),
    });
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    overlayRef.current?.releasePointerCapture(e.pointerId);
    dragOriginRef.current = null;
    if (!draftBox || !canvasSize || draftBox.widthPx <= 4 || draftBox.heightPx <= 4) {
      setDraftBox(null);
      return;
    }
    const pdfBox = boxToPdfCoords(draftBox, canvasSize.h);
    const id = nextFieldId(activeKind, fields);
    const key = nextKey();
    const newField: EditorField = {
      _key: key,
      id,
      kind: activeKind,
      label: '',
      description: '',
      required: false,
      prefill: null,
      page: draftBox.pageIdx + 1,
      ...pdfBox,
    };
    setFields((curr) => curr.concat(newField));
    setSelectedKey(key);
    setDraftBox(null);
  };

  // --- Field edits ------------------------------------------------
  // All edits address fields by stable ``_key`` — never the editable ``id``.

  const updateField = (key: string, patch: Partial<OnboardingFieldDefinition>) => {
    setFields((curr) => curr.map((f) => (f._key === key ? { ...f, ...patch } : f)));
  };

  const removeField = (key: string) => {
    setFields((curr) => curr.filter((f) => f._key !== key));
    setSelectedKey((curr) => (curr === key ? null : curr));
  };

  // Select a field for editing by its stable ``_key``: also sync the active type
  // chip to its kind and follow the view to its page.
  const selectFieldByKey = (key: string) => {
    const f = fields.find((x) => x._key === key);
    if (!f) return;
    setSelectedKey(key);
    setActiveKind(f.kind);
    if (f.page - 1 !== pageIdx) setPageIdx(f.page - 1);
  };

  // Clicking a type chip arms the draw tool AND cycles through fields of that
  // kind. A type with no fields just arms the draw tool and clears the panel.
  const selectKind = (kind: OnboardingFieldKind) => {
    setActiveKind(kind);
    const ofKind = fields.filter((f) => f.kind === kind);
    if (ofKind.length === 0) {
      setSelectedKey(null);
      return;
    }
    const currentIdx = ofKind.findIndex((f) => f._key === selectedKey);
    const next = ofKind[(currentIdx + 1) % ofKind.length];
    if (next) selectFieldByKey(next._key);
  };

  const invalidCount = useMemo(
    () => fields.filter((f) => fieldErrors(f, fields).length > 0).length,
    [fields],
  );

  const goPrev = () => setPageIdx((i) => Math.max(0, i - 1));
  const goNext = () => setPageIdx((i) => Math.min(pageCount - 1, i + 1));

  // Boxes visible on the current page (plus the in-flight draft box).
  const visibleBoxes: Array<{ field: EditorField | null; box: DrawnBox }> = [];
  if (canvasSize) {
    for (const field of fields) {
      if (field.page - 1 === pageIdx) {
        visibleBoxes.push({ field, box: pdfCoordsToBox(field, canvasSize.h) });
      }
    }
  }
  if (draftBox && draftBox.pageIdx === pageIdx) {
    visibleBoxes.push({ field: null, box: draftBox });
  }

  const selectedField = fields.find((f) => f._key === selectedKey) ?? null;
  const fieldsOnPage = fields.filter((f) => f.page - 1 === pageIdx).length;

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Pick a field type, then click and drag on the page to place it. Fill in
        its label and options in the panel.
      </p>
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

        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Field type">
          {FIELD_KINDS.map((kind) => (
            <KindToggle
              key={kind}
              kind={kind}
              activeKind={activeKind}
              count={fields.filter((f) => f.kind === kind).length}
              onClick={selectKind}
            />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_20rem] gap-4">
        {/* Canvas */}
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/40 p-3 overflow-auto max-h-[70vh]">
          {isLoadingDoc && (
            <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 p-6">
              <ArrowPathIcon className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              Loading template...
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
                aria-label="Template page — click and drag to draw the active field"
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
                {visibleBoxes.map(({ field, box }, i) => {
                  const kind = field?.kind ?? activeKind;
                  const meta = KIND_META[kind];
                  const isSelected = field !== null && field._key === selectedKey;
                  return (
                    <div
                      key={field ? field._key : `draft-${i}`}
                      className={`absolute pointer-events-none border-2 ${meta.box} ${
                        isSelected ? 'ring-2 ring-offset-1 ring-gray-900 dark:ring-white' : ''
                      }`}
                      style={{
                        left: `${box.leftPx}px`,
                        top: `${box.topPx}px`,
                        width: `${box.widthPx}px`,
                        height: `${box.heightPx}px`,
                      }}
                      aria-hidden={field === null ? 'true' : undefined}
                    >
                      <span
                        className={`absolute -top-5 left-0 rounded px-1.5 py-0.5 text-[10px] font-medium text-white ${meta.accent}`}
                      >
                        {field?.label?.trim() || meta.label}
                      </span>
                      {field !== null && (
                        <>
                          <button
                            type="button"
                            onPointerDown={(event) => {
                              event.preventDefault();
                              event.stopPropagation();
                            }}
                            onClick={(event) => {
                              event.preventDefault();
                              event.stopPropagation();
                              selectFieldByKey(field._key);
                            }}
                            className="pointer-events-auto absolute inset-0"
                            aria-label={`Select ${meta.label.toLowerCase()} field ${field.label || field.id}`}
                          />
                          <button
                            type="button"
                            onPointerDown={(event) => {
                              event.preventDefault();
                              event.stopPropagation();
                            }}
                            onClick={(event) => {
                              event.preventDefault();
                              event.stopPropagation();
                              removeField(field._key);
                            }}
                            className={`pointer-events-auto absolute -right-3 -top-3 inline-flex h-6 w-6 items-center justify-center rounded-full border border-white text-white shadow-sm hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-gray-900 dark:focus-visible:ring-white ${meta.accent}`}
                            aria-label={`Remove ${meta.label.toLowerCase()} field ${field.label || field.id}`}
                            title={`Remove ${meta.label.toLowerCase()} field`}
                          >
                            <XMarkIcon className="h-3.5 w-3.5" aria-hidden="true" />
                          </button>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {!isLoadingDoc && !docError && fieldsOnPage === 0 && !draftBox && (
            <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
              No fields on this page yet. Pick a type above, then drag a box on the page.
            </p>
          )}
        </div>

        {/* Per-field editor panel */}
        <FieldEditorPanel
          field={selectedField}
          allFields={fields}
          onChange={updateField}
          onRemove={removeField}
          onSelectKey={selectFieldByKey}
        />
      </div>

      {invalidCount > 0 && (
        <p aria-live="polite" className="text-xs text-amber-600 dark:text-amber-300">
          {invalidCount} field{invalidCount === 1 ? '' : 's'} need a label and a valid, unique id before saving.
        </p>
      )}
    </div>
  );
}

// ===========================================================================
// Modal wrapper — edit the fields of an EXISTING template (the per-row "Edit
// fields" entry point). Owns the field buffer + save lifecycle; delegates the
// authoring surface to the controlled body above.
// ===========================================================================

interface OnboardingTemplateEditorProps {
  isOpen: boolean;
  onClose: () => void;
  templateName: string;
  /** Object URL or remote URL pointing at the template PDF bytes. */
  pdfUrl: string;
  currentFields: OnboardingFieldDefinition[];
  onSave: (fields: OnboardingFieldDefinition[]) => Promise<void>;
}

export function OnboardingTemplateEditor({
  isOpen,
  onClose,
  templateName,
  pdfUrl,
  currentFields,
  onSave,
}: OnboardingTemplateEditorProps) {
  const [fields, setFields] = useState<OnboardingFieldDefinition[]>(currentFields);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const invalidCount = useMemo(
    () => fields.filter((f) => fieldErrors(f, fields).length > 0).length,
    [fields],
  );
  const canSave = invalidCount === 0 && !saving;

  const handleSave = async () => {
    if (invalidCount > 0) return;
    setSaving(true);
    setSaveError(null);
    try {
      await onSave(fields);
      onClose();
    } catch (err) {
      setSaveError(extractApiErrorDetail(err) ?? 'Failed to save fields');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={saving ? () => {} : onClose}
      title={`Define fields — ${templateName}`}
      size="full"
      closeOnOverlayClick={!saving}
    >
      <OnboardingTemplateEditorBody
        // Remount on a fresh PDF/template so the body re-seeds from currentFields.
        key={pdfUrl}
        pdfUrl={pdfUrl}
        value={fields}
        onChange={setFields}
      />

      {saveError && (
        <p
          role="alert"
          aria-live="polite"
          className="mt-4 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded px-3 py-2"
        >
          {saveError}
        </p>
      )}

      <ModalFooter>
        <Button type="button" variant="secondary" onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button
          type="button"
          variant="primary"
          onClick={handleSave}
          disabled={!canSave}
          isLoading={saving}
        >
          Save fields
        </Button>
      </ModalFooter>
    </Modal>
  );
}

interface KindToggleProps {
  kind: OnboardingFieldKind;
  activeKind: OnboardingFieldKind;
  count: number;
  onClick: (kind: OnboardingFieldKind) => void;
}

function KindToggle({ kind, activeKind, count, onClick }: KindToggleProps) {
  const isActive = kind === activeKind;
  const meta = KIND_META[kind];
  const Icon = meta.icon;
  return (
    <button
      type="button"
      onClick={() => onClick(kind)}
      className={`inline-flex items-center gap-1.5 rounded border px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 ${
        isActive
          ? 'border-primary-500 bg-primary-50 text-primary-700 dark:border-primary-400 dark:bg-primary-950/30 dark:text-primary-300'
          : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700'
      }`}
      aria-pressed={isActive}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {meta.label}
      <span className="text-gray-400 dark:text-gray-500" style={{ fontVariantNumeric: 'tabular-nums' }}>
        {count}
      </span>
    </button>
  );
}

interface FieldEditorPanelProps {
  field: EditorField | null;
  allFields: EditorField[];
  /** All address the field by its stable internal ``_key``. */
  onChange: (key: string, patch: Partial<OnboardingFieldDefinition>) => void;
  onRemove: (key: string) => void;
  /** Jump the editor to another field (used by the same-kind stepper). */
  onSelectKey: (key: string) => void;
}

function FieldEditorPanel({ field, allFields, onChange, onRemove, onSelectKey }: FieldEditorPanelProps) {
  if (!field) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 dark:border-gray-600 p-4 text-sm text-gray-500 dark:text-gray-400">
        Select a field on the page — or click a type above — to edit its label,
        description, and options.
      </div>
    );
  }

  const errors = fieldErrors(field, allFields);

  // Same-kind siblings, so a doc with e.g. 2 signatures can step between them
  // right here in the panel (◀ 1 / 2 ▶).
  const siblings = allFields.filter((f) => f.kind === field.kind);
  const siblingIdx = siblings.findIndex((f) => f._key === field._key);
  const hasSiblings = siblings.length > 1;
  const kindLabel = KIND_META[field.kind].label.toLowerCase();
  const stepTo = (offset: number) => {
    const target = siblings[(siblingIdx + offset + siblings.length) % siblings.length];
    if (target) onSelectKey(target._key);
  };

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <h3 className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
            {KIND_META[field.kind].label} field
          </h3>
          {hasSiblings && (
            <span className="inline-flex items-center gap-0.5 rounded-md border border-gray-200 dark:border-gray-600">
              <button
                type="button"
                onClick={() => stepTo(-1)}
                className="inline-flex h-6 w-6 items-center justify-center rounded-l-md text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                aria-label={`Previous ${kindLabel} field`}
              >
                <ArrowLeftIcon className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
              <span
                className="px-1 text-xs text-gray-500 dark:text-gray-400"
                style={{ fontVariantNumeric: 'tabular-nums' }}
                aria-label={`${kindLabel} field ${siblingIdx + 1} of ${siblings.length}`}
              >
                {siblingIdx + 1}/{siblings.length}
              </span>
              <button
                type="button"
                onClick={() => stepTo(1)}
                className="inline-flex h-6 w-6 items-center justify-center rounded-r-md text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                aria-label={`Next ${kindLabel} field`}
              >
                <ArrowRightIcon className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => onRemove(field._key)}
          className="shrink-0 text-xs font-medium text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 rounded"
        >
          Remove
        </button>
      </div>

      <Input
        label="Field id"
        value={field.id}
        onChange={(e) => onChange(field._key, { id: e.target.value })}
        name="onboarding-field-id"
        autoComplete="off"
        spellCheck={false}
        placeholder="e.g. ein_number..."
        helperText="Lowercase letters, numbers, and underscores; unique within the document."
      />

      <Input
        label="Label"
        value={field.label}
        onChange={(e) => onChange(field._key, { label: e.target.value })}
        name="onboarding-field-label"
        autoComplete="off"
        placeholder="e.g. Federal EIN..."
      />

      <Input
        label="Description (optional)"
        value={field.description ?? ''}
        onChange={(e) => onChange(field._key, { description: e.target.value })}
        name="onboarding-field-description"
        autoComplete="off"
        placeholder="Shown to the client as a hint..."
      />

      <Select
        label="Prefill"
        value={field.prefill ?? ''}
        onChange={(e) =>
          onChange(field._key, {
            prefill: (e.target.value || null) as OnboardingFieldPrefill,
          })
        }
        options={ESIGN_PREFILL_OPTIONS}
        helperText="Auto-fill the value from the linked contact or company."
      />

      <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
        <input
          type="checkbox"
          checked={field.required}
          onChange={(e) => onChange(field._key, { required: e.target.checked })}
          className="h-4 w-4 rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
        />
        Required
      </label>

      <p
        className="text-xs text-gray-400 dark:text-gray-500"
        style={{ fontVariantNumeric: 'tabular-nums' }}
      >
        Page {field.page} · {Math.round(field.w)}×{Math.round(field.h)} pt
      </p>

      {errors.length > 0 && (
        <ul aria-live="polite" className="text-xs text-red-600 dark:text-red-400 space-y-0.5">
          {errors.map((err) => (
            <li key={err}>{err}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default OnboardingTemplateEditor;

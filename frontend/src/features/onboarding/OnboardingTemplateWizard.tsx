/**
 * "Create Onboarding Template" wizard.
 *
 * One guided flow from nothing → a ready-to-send template:
 *   Kind → Basics → Build → Review/Create.
 *
 * ARCHITECTURE = Option B: ALL authoring is local. The wizard creates NOTHING
 * on the server until "Create" — the questionnaire/upload field list and the
 * e-sign field placements (against a local ``URL.createObjectURL`` preview of
 * the picked PDF) live entirely in component state. Modelled on
 * ``OnboardingPacketWizard``: one Modal, a Step union, a step-indicator <ol>,
 * derived per-step validation, a Back/Next/Create footer, and a flat draft.
 *
 * "Can't finish empty" (new client policy): a questionnaire/upload needs ≥1
 * valid field; an e-sign needs ≥1 SIGNATURE field — matching the server-side
 * signature-aware send guard. Commit sequences and recovery live in
 * {@link handleCreate}.
 */
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getDocument } from 'pdfjs-dist';
import {
  ArrowUpTrayIcon,
  DocumentTextIcon,
  PencilSquareIcon,
} from '@heroicons/react/24/outline';
import { Modal, ModalFooter, Button, Input, Badge } from '../../components/ui';
import {
  createOnboardingTemplate,
  uploadOnboardingTemplatePdf,
  updateOnboardingTemplate,
  retireOnboardingTemplate,
  restoreOnboardingTemplate,
  listOnboardingTemplates,
  ONBOARDING_PDF_MAX_BYTES,
} from '../../api/onboarding';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
import type {
  OnboardingDocumentKind,
  OnboardingFieldDefinition,
  OnboardingQuestionnaireField,
  OnboardingTemplate,
} from '../../types';
import {
  OnboardingFormBuilderBody,
  validate as validateFormFields,
  cleanField,
} from './OnboardingFormBuilder';
// Importing the editor module also installs the pdf.js worker (module scope),
// which the PDF pre-check below relies on.
import { OnboardingTemplateEditorBody } from './OnboardingTemplateEditor';
import { fieldErrors } from './fieldKinds';

/** A template with more fields than this is un-fillable: the public fill page
 *  caps a single document at 200 fields per body (backend MAX_FIELD_COUNT). */
const MAX_FIELDS = 200;

type Step = 'kind' | 'basics' | 'build' | 'review';
const STEPS: { key: Step; label: string }[] = [
  { key: 'kind', label: 'Type' },
  { key: 'basics', label: 'Basics' },
  { key: 'build', label: 'Build' },
  { key: 'review', label: 'Review' },
];

interface KindOption {
  value: OnboardingDocumentKind;
  label: string;
  hint: string;
  icon: typeof DocumentTextIcon;
}
const KIND_OPTIONS: KindOption[] = [
  {
    value: 'questionnaire',
    label: 'Questionnaire',
    hint: 'Ask typed questions — text, choices, dates. The client answers a web form.',
    icon: DocumentTextIcon,
  },
  {
    value: 'upload_request',
    label: 'File upload',
    hint: 'Collect files — ID, brand assets, documents. Each field is a labelled upload slot.',
    icon: ArrowUpTrayIcon,
  },
  {
    value: 'esign_pdf',
    label: 'E-sign PDF',
    hint: 'Upload a PDF and place signature / text / date fields for the client to sign.',
    icon: PencilSquareIcon,
  },
];

interface OnboardingTemplateWizardProps {
  isOpen: boolean;
  onClose: () => void;
  /** Called after a template is created (the wizard already toasts + closes). */
  onCreated?: () => void;
}

/** Run the pdf.js pre-check the backend does only at upload, but client-side at
 *  pick time: reject encrypted (password) PDFs and any non-zero page rotation
 *  (a rotated mediabox would misplace every field). Returns an error string or
 *  ``null`` when the PDF is placeable. */
async function precheckPdf(file: File): Promise<string | null> {
  let doc;
  try {
    const buf = await file.arrayBuffer();
    doc = await getDocument({ data: new Uint8Array(buf) }).promise;
  } catch (err) {
    const name = (err as { name?: string } | undefined)?.name;
    if (name === 'PasswordException') {
      return 'Encrypted / password-protected PDFs are not supported.';
    }
    return 'This file is not a readable PDF.';
  }
  try {
    for (let i = 1; i <= doc.numPages; i += 1) {
      const page = await doc.getPage(i);
      if (((page.rotate % 360) + 360) % 360 !== 0) {
        return "Rotated PDF pages aren't supported yet; please upload an unrotated PDF.";
      }
    }
    return null;
  } finally {
    void doc.destroy();
  }
}

export function OnboardingTemplateWizard({
  isOpen,
  onClose,
  onCreated,
}: OnboardingTemplateWizardProps) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>('kind');
  const [kind, setKind] = useState<OnboardingDocumentKind>('questionnaire');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [serviceTag, setServiceTag] = useState('');

  // Build-step drafts (Option B — local only).
  const [formFields, setFormFields] = useState<OnboardingQuestionnaireField[]>([]);
  const [esignFile, setEsignFile] = useState<File | null>(null);
  const [esignPdfUrl, setEsignPdfUrl] = useState<string | null>(null);
  const [esignFields, setEsignFields] = useState<OnboardingFieldDefinition[]>([]);
  const [pdfCheckError, setPdfCheckError] = useState<string | null>(null);
  const [checkingPdf, setCheckingPdf] = useState(false);

  // Commit state (a state machine so a partial e-sign failure resumes the
  // remaining steps against the SAME created template — re-creating would
  // collide on the unique name, which the failed shell still holds).
  const [submitting, setSubmitting] = useState(false);
  const [createdTemplateId, setCreatedTemplateId] = useState<number | null>(null);
  const [uploaded, setUploaded] = useState(false);
  const [commitError, setCommitError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [restoreCandidate, setRestoreCandidate] = useState<OnboardingTemplate | null>(null);

  const objectUrlRef = useRef<string | null>(null);
  const nameInputRef = useRef<HTMLInputElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const descId = useId();

  const revokeObjectUrl = () => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  };

  // Revoke the preview object URL on unmount.
  useEffect(() => () => revokeObjectUrl(), []);

  const reset = () => {
    setStep('kind');
    setKind('questionnaire');
    setName('');
    setDescription('');
    setServiceTag('');
    setFormFields([]);
    setEsignFile(null);
    revokeObjectUrl();
    setEsignPdfUrl(null);
    setEsignFields([]);
    setPdfCheckError(null);
    setCheckingPdf(false);
    setSubmitting(false);
    setCreatedTemplateId(null);
    setUploaded(false);
    setCommitError(null);
    setNameError(null);
    setRestoreCandidate(null);
  };

  const close = () => {
    if (submitting) return; // don't abandon a commit in flight
    reset();
    onClose();
  };

  const isEsign = kind === 'esign_pdf';
  const trimmedName = name.trim();

  // --- Derived per-step validity -------------------------------------------
  const formFieldsClean = useMemo(() => formFields.map(cleanField), [formFields]);
  const formValid = validateFormFields(formFieldsClean) === null;
  const esignSignatureCount = useMemo(
    () => esignFields.filter((f) => f.kind === 'signature').length,
    [esignFields],
  );
  const esignFieldsValid =
    esignFields.length > 0 &&
    esignFields.every((f) => fieldErrors(f, esignFields).length === 0);

  const fieldCount = isEsign ? esignFields.length : formFields.length;
  const overFieldCap = fieldCount > MAX_FIELDS;

  const buildValid = isEsign
    ? Boolean(esignFile) &&
      Boolean(esignPdfUrl) &&
      pdfCheckError === null &&
      esignSignatureCount >= 1 &&
      esignFieldsValid &&
      !overFieldCap
    : formValid && formFields.length >= 1 && !overFieldCap;

  const canCreate = trimmedName.length > 0 && buildValid && !submitting;

  // --- Step navigation + managed focus -------------------------------------
  const stepIndex = STEPS.findIndex((s) => s.key === step);

  // After a step change, move focus to that step's primary control.
  useEffect(() => {
    if (!isOpen) return;
    if (step === 'basics') {
      nameInputRef.current?.focus();
    } else {
      headingRef.current?.focus();
    }
  }, [step, isOpen]);

  const goToBuildOrReview = () => {
    // Switching to a different kind mid-build would orphan kind-specific drafts;
    // the Kind step disables Next once any build content exists (see canLeaveKind).
    setStep(step === 'basics' ? 'build' : 'review');
  };

  // --- PDF pick + pre-check ------------------------------------------------
  const handlePickPdf = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-picking the same file
    if (!file) return;
    if (file.type !== 'application/pdf') {
      setPdfCheckError('Please choose a PDF file.');
      return;
    }
    if (file.size > ONBOARDING_PDF_MAX_BYTES) {
      setPdfCheckError('PDF is too large (25 MB max).');
      return;
    }
    setCheckingPdf(true);
    setPdfCheckError(null);
    const error = await precheckPdf(file);
    setCheckingPdf(false);
    if (error) {
      setPdfCheckError(error);
      return;
    }
    // Accepted: swap in a fresh local preview and CLEAR any prior placements
    // (old coords are meaningless against a new PDF) + reset the commit machine.
    revokeObjectUrl();
    const url = URL.createObjectURL(file);
    objectUrlRef.current = url;
    setEsignPdfUrl(url);
    setEsignFile(file);
    setEsignFields([]);
    setCreatedTemplateId(null);
    setUploaded(false);
  };

  // --- Commit --------------------------------------------------------------
  const handleCommitError = async (err: unknown) => {
    const detail = extractApiErrorDetail(err) ?? 'Failed to create template';
    // A duplicate-name 422 is reported as a plain string by the service. If it
    // fired at the create call (no template made yet), surface it on the Name
    // field and offer to restore a retired same-name shell.
    if (createdTemplateId == null && /already exists/i.test(detail)) {
      setNameError(detail);
      setStep('basics');
      try {
        const retired = await listOnboardingTemplates({ include_inactive: true });
        const match = retired.find(
          (t) => !t.is_active && t.name.trim().toLowerCase() === trimmedName.toLowerCase(),
        );
        setRestoreCandidate(match ?? null);
      } catch {
        setRestoreCandidate(null);
      }
      return;
    }
    setCommitError(detail);
  };

  const handleCreate = async () => {
    if (!canCreate || submitting) return;
    setSubmitting(true);
    setCommitError(null);
    setNameError(null);
    setRestoreCandidate(null);
    const service_tag = serviceTag.trim() || undefined; // "" → OMIT (null), never ""
    const baseDescription = description.trim() || null;
    try {
      if (!isEsign) {
        const tmpl = await createOnboardingTemplate({
          name: trimmedName,
          kind,
          description: baseDescription,
          service_tag,
          field_definitions: formFieldsClean,
        });
        finishSuccess(tmpl.name);
        return;
      }

      // E-sign — 3-call commit (transient shell only at commit), resumable.
      let id = createdTemplateId;
      if (id == null) {
        const tmpl = await createOnboardingTemplate({
          name: trimmedName,
          kind: 'esign_pdf',
          description: baseDescription,
          service_tag,
          // No fields / no requires_esign — both 422 at create for esign_pdf.
        });
        id = tmpl.id;
        setCreatedTemplateId(id);
      }
      if (!uploaded) {
        // First upload stays pdf_version 1 and does NOT clear fields.
        await uploadOnboardingTemplatePdf(id, esignFile as File);
        setUploaded(true);
      }
      // Combined PATCH: fields (≥1 signature) + requires_esign, optimistic-locked
      // on pdf_version 1 (the happy path never 409s).
      const finalTmpl = await updateOnboardingTemplate(id, {
        field_definitions: esignFields,
        pdf_version: 1,
        requires_esign: true,
      });
      finishSuccess(finalTmpl.name);
    } catch (err) {
      await handleCommitError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const finishSuccess = (createdName: string) => {
    queryClient.invalidateQueries({ queryKey: ['onboarding-templates'] });
    showSuccess(`Template “${createdName}” created.`);
    onCreated?.();
    reset();
    onClose();
  };

  // Best-effort retire of a stranded e-sign shell when the user gives up on a
  // partial failure (the server-side signature guard already makes it
  // un-sendable; this just hides it from the library).
  const handleDiscardShell = async () => {
    if (createdTemplateId == null) return;
    try {
      await retireOnboardingTemplate(createdTemplateId);
    } catch {
      /* best-effort — the §A guard keeps the shell un-sendable regardless */
    }
    queryClient.invalidateQueries({ queryKey: ['onboarding-templates'] });
    close();
  };

  const handleRestore = async () => {
    if (!restoreCandidate) return;
    try {
      await restoreOnboardingTemplate(restoreCandidate.id);
      showSuccess(`Restored “${restoreCandidate.name}”. Edit it from the library.`);
      queryClient.invalidateQueries({ queryKey: ['onboarding-templates'] });
      reset();
      onClose();
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to restore template');
    }
  };

  // Switching kind is only offered before any build content exists, so kind +
  // build drafts can't desync. Once on Build with content, Back to Kind warns.
  const hasBuildContent = isEsign
    ? Boolean(esignFile) || esignFields.length > 0
    : formFields.length > 0;

  const dirty =
    trimmedName.length > 0 || description.trim().length > 0 || hasBuildContent;

  return (
    <Modal
      isOpen={isOpen}
      onClose={close}
      title="Create onboarding template"
      size="full"
      confirmClose={dirty && !submitting}
      confirmCloseMessage="Your new template hasn't been created yet. Discard it?"
      closeOnOverlayClick={!submitting}
    >
      {/* Step indicator */}
      <ol className="mb-4 flex flex-wrap items-center gap-2 text-xs font-medium" aria-label="Wizard steps">
        {STEPS.map((s, i) => (
          <li key={s.key} className="flex items-center gap-2">
            <span
              aria-current={step === s.key ? 'step' : undefined}
              className={
                step === s.key
                  ? 'rounded-full bg-primary-600 px-2.5 py-1 text-white'
                  : i < stepIndex
                    ? 'rounded-full bg-primary-100 px-2.5 py-1 text-primary-700 dark:bg-primary-950/40 dark:text-primary-300'
                    : 'rounded-full bg-gray-100 px-2.5 py-1 text-gray-500 dark:bg-gray-700 dark:text-gray-300'
              }
            >
              {i + 1}. {s.label}
            </span>
            {i < STEPS.length - 1 && (
              <span aria-hidden="true" className="text-gray-300">
                ›
              </span>
            )}
          </li>
        ))}
      </ol>

      {/* ---------------------------------------------------------------- Kind */}
      {step === 'kind' && (
        <div className="space-y-4">
          <h2
            ref={headingRef}
            tabIndex={-1}
            className="text-base font-semibold text-gray-900 dark:text-gray-100 focus:outline-none"
          >
            What kind of document is this?
          </h2>
          <KindRadioGroup value={kind} onChange={setKind} />
        </div>
      )}

      {/* -------------------------------------------------------------- Basics */}
      {step === 'basics' && (
        <div className="space-y-4">
          <h2
            ref={headingRef}
            tabIndex={-1}
            className="text-base font-semibold text-gray-900 dark:text-gray-100 focus:outline-none"
          >
            Name this template
          </h2>
          <Input
            ref={nameInputRef}
            label="Name"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (nameError) setNameError(null);
              if (restoreCandidate) setRestoreCandidate(null);
            }}
            name="onboarding-template-name"
            autoComplete="off"
            placeholder="e.g. New client intake packet..."
            required
            error={nameError ?? undefined}
          />
          {restoreCandidate && (
            <div
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm dark:border-amber-800 dark:bg-amber-900/20"
              aria-live="polite"
            >
              <span className="text-amber-800 dark:text-amber-200 text-pretty">
                A retired template named “{restoreCandidate.name}” already exists.
                Restore it instead?
              </span>
              <Button type="button" variant="secondary" size="sm" onClick={handleRestore}>
                Restore
              </Button>
            </div>
          )}
          <div>
            <label
              htmlFor={descId}
              className="block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Description (optional)
            </label>
            <textarea
              id={descId}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus-visible:border-primary-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500"
              placeholder="What this template is for…"
            />
          </div>
          <Input
            label="Service tag (optional)"
            value={serviceTag}
            onChange={(e) => setServiceTag(e.target.value)}
            name="onboarding-template-service-tag"
            autoComplete="off"
            spellCheck={false}
            placeholder="Leave blank for a universal template..."
            helperText="Scopes the template to one service. Blank = universal."
          />
        </div>
      )}

      {/* --------------------------------------------------------------- Build */}
      {step === 'build' && (
        <div className="space-y-4">
          <h2
            ref={headingRef}
            tabIndex={-1}
            className="text-base font-semibold text-gray-900 dark:text-gray-100 focus:outline-none"
          >
            {isEsign ? 'Place the fields' : 'Build the form'}
          </h2>

          {!isEsign && (
            <OnboardingFormBuilderBody
              kind={kind as 'questionnaire' | 'upload_request'}
              value={formFields}
              onChange={setFormFields}
            />
          )}

          {isEsign && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf"
                  className="sr-only"
                  aria-hidden="true"
                  tabIndex={-1}
                  onChange={handlePickPdf}
                />
                <Button
                  type="button"
                  variant="secondary"
                  leftIcon={<ArrowUpTrayIcon className="h-4 w-4" aria-hidden="true" />}
                  onClick={() => fileInputRef.current?.click()}
                  isLoading={checkingPdf}
                >
                  {esignPdfUrl ? 'Replace PDF' : 'Choose PDF'}
                </Button>
                {esignFile && (
                  <span className="min-w-0 truncate text-sm text-gray-600 dark:text-gray-300">
                    {esignFile.name}
                  </span>
                )}
              </div>

              {pdfCheckError && (
                <p
                  role="alert"
                  aria-live="polite"
                  className="text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded px-3 py-2"
                >
                  {pdfCheckError}
                </p>
              )}

              {esignPdfUrl && !pdfCheckError && (
                <OnboardingTemplateEditorBody
                  key={esignPdfUrl}
                  pdfUrl={esignPdfUrl}
                  value={esignFields}
                  onChange={setEsignFields}
                />
              )}

              {esignPdfUrl && esignSignatureCount === 0 && (
                <p aria-live="polite" className="text-xs text-amber-600 dark:text-amber-300">
                  Place at least one signature field — an e-sign document can’t be
                  sent without one.
                </p>
              )}
              {!esignPdfUrl && !pdfCheckError && (
                <p className="text-sm text-gray-500 dark:text-gray-400 text-pretty">
                  Choose the PDF to sign, then drag signature, text, and date
                  fields onto it.
                </p>
              )}
            </div>
          )}

          {overFieldCap && (
            <p role="alert" aria-live="polite" className="text-sm text-red-700 dark:text-red-400">
              A document can hold at most {MAX_FIELDS} fields ({fieldCount} placed).
            </p>
          )}
        </div>
      )}

      {/* -------------------------------------------------------------- Review */}
      {step === 'review' && (
        <div className="space-y-4">
          <h2
            ref={headingRef}
            tabIndex={-1}
            className="text-base font-semibold text-gray-900 dark:text-gray-100 focus:outline-none"
          >
            Review &amp; create
          </h2>
          <dl className="space-y-2 text-sm">
            <ReviewRow label="Type">
              {KIND_OPTIONS.find((o) => o.value === kind)?.label}
            </ReviewRow>
            <ReviewRow label="Name">{trimmedName}</ReviewRow>
            {description.trim() && (
              <ReviewRow label="Description">
                <span className="text-pretty">{description.trim()}</span>
              </ReviewRow>
            )}
            <ReviewRow label="Service">
              {serviceTag.trim() ? (
                serviceTag.trim()
              ) : (
                <span className="text-gray-400">Universal</span>
              )}
            </ReviewRow>
            <ReviewRow label="Fields">
              {isEsign
                ? `${esignFields.length} placed · ${esignSignatureCount} signature`
                : `${formFields.length} field${formFields.length === 1 ? '' : 's'}`}
            </ReviewRow>
          </dl>
          <div className="flex items-center gap-2">
            {buildValid ? (
              <Badge variant="green" size="sm">
                Ready to send
              </Badge>
            ) : (
              <Badge variant="yellow" size="sm">
                Needs setup
              </Badge>
            )}
          </div>

          {commitError && (
            <div
              className="space-y-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 dark:border-red-800 dark:bg-red-900/20"
              role="alert"
              aria-live="polite"
            >
              <p className="text-sm text-red-700 dark:text-red-300 text-pretty">
                {commitError}
                {createdTemplateId != null && ' — “Create template” retries the remaining steps.'}
              </p>
              {createdTemplateId != null && (
                <Button type="button" variant="ghost" size="sm" onClick={handleDiscardShell}>
                  Discard and close
                </Button>
              )}
            </div>
          )}
        </div>
      )}

      <ModalFooter>
        {step === 'kind' && (
          <>
            <Button variant="secondary" onClick={close}>
              Cancel
            </Button>
            <Button onClick={() => setStep('basics')}>Next: basics</Button>
          </>
        )}
        {step === 'basics' && (
          <>
            <Button variant="secondary" onClick={() => setStep('kind')}>
              Back
            </Button>
            <Button onClick={goToBuildOrReview} disabled={trimmedName.length === 0}>
              Next: build
            </Button>
          </>
        )}
        {step === 'build' && (
          <>
            <Button variant="secondary" onClick={() => setStep('basics')}>
              Back
            </Button>
            <Button onClick={() => setStep('review')} disabled={!buildValid}>
              Next: review
            </Button>
          </>
        )}
        {step === 'review' && (
          <>
            <Button variant="secondary" onClick={() => setStep('build')} disabled={submitting}>
              Back
            </Button>
            <Button onClick={handleCreate} disabled={!canCreate} isLoading={submitting}>
              Create template
            </Button>
          </>
        )}
      </ModalFooter>
    </Modal>
  );
}

function ReviewRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2">
      <dt className="w-24 flex-shrink-0 text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="min-w-0 flex-1 text-gray-900 dark:text-gray-100">{children}</dd>
    </div>
  );
}

/**
 * A conformant ARIA radiogroup with roving tabindex + arrow-key navigation —
 * deliberately NOT the segmented-button radios elsewhere (which trap a tab stop
 * per option). Exactly one radio is tabbable; arrows move focus AND selection.
 */
function KindRadioGroup({
  value,
  onChange,
}: {
  value: OnboardingDocumentKind;
  onChange: (k: OnboardingDocumentKind) => void;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIdx = KIND_OPTIONS.findIndex((o) => o.value === value);

  const focusAndSelect = (idx: number) => {
    const opt = KIND_OPTIONS[idx];
    if (!opt) return;
    onChange(opt.value);
    refs.current[idx]?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent, idx: number) => {
    const last = KIND_OPTIONS.length - 1;
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
      e.preventDefault();
      focusAndSelect(idx === last ? 0 : idx + 1);
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
      e.preventDefault();
      focusAndSelect(idx === 0 ? last : idx - 1);
    } else if (e.key === 'Home') {
      e.preventDefault();
      focusAndSelect(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      focusAndSelect(last);
    }
  };

  return (
    <div role="radiogroup" aria-label="Document type" className="grid gap-2 sm:grid-cols-3">
      {KIND_OPTIONS.map((opt, idx) => {
        const Icon = opt.icon;
        const checked = opt.value === value;
        return (
          <button
            key={opt.value}
            ref={(el) => {
              refs.current[idx] = el;
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked || (selectedIdx === -1 && idx === 0) ? 0 : -1}
            onClick={() => onChange(opt.value)}
            onKeyDown={(e) => onKeyDown(e, idx)}
            className={`flex flex-col gap-1.5 rounded-lg border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 ${
              checked
                ? 'border-primary-500 bg-primary-50 dark:border-primary-400 dark:bg-primary-950/30'
                : 'border-gray-200 bg-white hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700'
            }`}
          >
            <span className="flex items-center gap-2">
              <Icon
                className={`h-5 w-5 ${checked ? 'text-primary-600 dark:text-primary-300' : 'text-gray-400'}`}
                aria-hidden="true"
              />
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {opt.label}
              </span>
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400 text-pretty">{opt.hint}</span>
          </button>
        );
      })}
    </div>
  );
}

export default OnboardingTemplateWizard;

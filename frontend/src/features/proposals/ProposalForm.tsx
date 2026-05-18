import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Button, SearchableSelect } from '../../components/ui';
import { MissingRelationDialog } from '../../components/shared/MissingRelationDialog';
import { useMissingRelationConfirm } from '../../hooks/useMissingRelationConfirm';
import BillingTermsField, { type BillingTermsValue } from '../../components/forms/BillingTermsField';
import { useContacts } from '../../hooks/useContacts';
import { useCompanies } from '../../hooks/useCompanies';
import { useFormSubmitShortcut } from '../../hooks/useSubmitShortcut';
import { useUnsavedChangesWarning } from '../../hooks/useUnsavedChangesWarning';
import { PendingMasterContractField } from './PendingMasterContractField';
import { useAuthStore } from '../../store/authStore';
import type { ProposalCreate } from '../../types';
import {
  clearProposalDraft,
  formatProposalDraftTime,
  getProposalDraftKey,
  isProposalFormDraftEmpty,
  readProposalDraft,
  writeProposalDraft,
  type ProposalFormDraftFields,
  type ProposalFormDraftRecord,
  type ProposalFormDraftValue,
} from './proposalDrafts';

/** Progress reported by the parent while signing PDFs upload after a
 *  successful create. Lets the submit button announce which file is
 *  currently uploading instead of going dark mid-loop. */
export interface SigningUploadStatus {
  current: number;
  total: number;
  fileName: string;
}

interface ProposalFormProps {
  /** Called with form data plus pending signing PDFs (create flow only).
   *  The parent uploads them after the proposal id exists; signature boxes
   *  are placed from the proposal detail page before sending. */
  onSubmit: (data: ProposalCreate, pendingSigningDocs?: File[]) => void | Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
  /** Non-null while the parent is uploading the stashed signing PDFs.
   *  Drives an in-progress label so the user can see N/M progress instead
   *  of staring at a frozen modal between create-row and navigate. */
  signingUploadStatus?: SigningUploadStatus | null;
  initialData?: Partial<ProposalCreate>;
  /** Form mode discriminator. Edit mode no longer carries the
   *  master-contract widget — that surface lives on the detail page
   *  sidebar so it's discoverable without opening the modal. */
  proposalId?: number;
}

export function ProposalForm({
  onSubmit,
  onCancel,
  isLoading,
  signingUploadStatus = null,
  initialData,
  proposalId,
}: ProposalFormProps) {
  const isCreating = proposalId == null;
  const userId = useAuthStore((s) => s.user?.id);
  const draftMode = isCreating ? 'create' : 'edit';
  const draftKey = getProposalDraftKey(userId, draftMode, proposalId);
  const [pendingSigningDocs, setPendingSigningDocs] = useState<File[]>([]);
  const [restoredSigningDocNames, setRestoredSigningDocNames] = useState<string[]>([]);
  const [draftPrompt, setDraftPrompt] = useState<ProposalFormDraftRecord | null>(null);
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);
  const [autosaveBlocked, setAutosaveBlocked] = useState(false);
  const [externalDraftUpdated, setExternalDraftUpdated] = useState(false);
  const [reattachError, setReattachError] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const hasUserEditedRef = useRef(false);
  const submittingRef = useRef(false);
  const submittedSuccessfullyRef = useRef(false);
  const [submitCycle, setSubmitCycle] = useState(0);
  const [searchParams] = useSearchParams();
  // Pre-fill any of the Related Records from URL query params so
  // navigating "Create Proposal" from a contact / company detail page
  // lands the user on a form with that link already selected.
  const parseUrlId = (key: string): number | null => {
    const raw = searchParams.get(key);
    if (!raw) return null;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : null;
  };
  const urlContactId = parseUrlId('contact_id');
  const urlCompanyId = parseUrlId('company_id');

  const buildInitialFormData = (): ProposalFormDraftFields => ({
    title: initialData?.title ?? '',
    content: initialData?.content ?? '',
    contactId: (initialData?.contact_id ?? urlContactId) as number | null,
    companyId: (initialData?.company_id ?? urlCompanyId) as number | null,
    executiveSummary: initialData?.executive_summary ?? '',
    scopeOfWork: initialData?.scope_of_work ?? '',
    pricingSection: initialData?.pricing_section ?? '',
    timelineField: initialData?.timeline ?? '',
    terms: initialData?.terms ?? '',
    validUntil: initialData?.valid_until ?? '',
    termsAndConditions: initialData?.terms_and_conditions ?? '',
  });

  const buildInitialBilling = (): BillingTermsValue => ({
    payment_type: initialData?.payment_type ?? 'one_time',
    recurring_interval: initialData?.recurring_interval ?? null,
    recurring_interval_count: initialData?.recurring_interval_count ?? null,
    amount: initialData?.amount != null ? String(initialData.amount) : '',
    currency: initialData?.currency ?? 'USD',
  });

  const [formData, setFormData] = useState<ProposalFormDraftFields>(buildInitialFormData);

  // Billing terms (pre-cast amount to string for the controlled input).
  const [billing, setBilling] = useState<BillingTermsValue>(buildInitialBilling);

  // `touched` flips true on first edit; drives the beforeunload warning.
  // ProposalForm uses `useState` so we can't lean on react-hook-form's
  // `formState.isDirty`. Auto-fill from URL params does NOT count.
  const [touched, setTouched] = useState(false);
  useUnsavedChangesWarning(touched);

  const markTouched = useCallback((options?: { discardPrompt?: boolean }) => {
    hasUserEditedRef.current = true;
    if (!submittingRef.current) {
      submittedSuccessfullyRef.current = false;
    }
    if (options?.discardPrompt && draftPrompt) {
      clearProposalDraft(draftKey);
      setDraftPrompt(null);
      setLastSavedAt(null);
      setRestoredSigningDocNames([]);
    }
    setTouched(true);
    setReattachError(false);
  }, [draftKey, draftPrompt]);

  useEffect(() => {
    const saved = readProposalDraft(draftKey);
    setRestoredSigningDocNames([]);
    setExternalDraftUpdated(false);
    setAutosaveBlocked(false);
    setReattachError(false);
    submittedSuccessfullyRef.current = false;
    if (!saved || isProposalFormDraftEmpty(saved.value) || hasUserEditedRef.current) {
      setLastSavedAt(null);
      setDraftPrompt(null);
      return;
    }
    setLastSavedAt(saved.updatedAt);
    setDraftPrompt(saved);
  }, [draftKey]);

  // Today in user's LOCAL timezone (YYYY-MM-DD) for `min` on Valid Until.
  // Only applied when creating a new proposal — see `min` site below.
  const todayDate = useMemo(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }, []);
  const isEditing = !!initialData;
  const formDisabled = !!isLoading || isSubmitting || signingUploadStatus != null;

  const formRef = useFormSubmitShortcut();

  const updateField = <K extends keyof typeof formData>(field: K, value: typeof formData[K]) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    markTouched({ discardPrompt: true });
  };

  const selectedSigningDocNames = useMemo(
    () => pendingSigningDocs.map((file) => file.name),
    [pendingSigningDocs],
  );

  const missingRestoredSigningDocNames = useMemo(() => {
    const selectedNameCounts = new Map<string, number>();
    selectedSigningDocNames.forEach((name) => {
      selectedNameCounts.set(name, (selectedNameCounts.get(name) ?? 0) + 1);
    });
    return restoredSigningDocNames.filter((name) => {
      const count = selectedNameCounts.get(name) ?? 0;
      if (count <= 0) return true;
      selectedNameCounts.set(name, count - 1);
      return false;
    });
  }, [restoredSigningDocNames, selectedSigningDocNames]);

  const currentDraftValue = useMemo<ProposalFormDraftValue>(
    () => ({
      formData,
      billing,
      pendingSigningDocNames: [
        ...selectedSigningDocNames,
        ...missingRestoredSigningDocNames,
      ],
    }),
    [billing, formData, missingRestoredSigningDocNames, selectedSigningDocNames],
  );

  useEffect(() => {
    if (
      !draftKey ||
      !touched ||
      draftPrompt ||
      submittingRef.current ||
      submittedSuccessfullyRef.current
    ) return;
    const timer = window.setTimeout(() => {
      if (submittingRef.current || submittedSuccessfullyRef.current) return;
      if (isProposalFormDraftEmpty(currentDraftValue)) {
        clearProposalDraft(draftKey);
        setLastSavedAt(null);
        return;
      }
      const saved = writeProposalDraft(
        draftKey,
        draftMode,
        proposalId,
        currentDraftValue,
      );
      if (!saved) {
        setAutosaveBlocked(true);
        return;
      }
      setAutosaveBlocked(false);
      setLastSavedAt(saved.updatedAt);
    }, 500);

    return () => window.clearTimeout(timer);
  }, [currentDraftValue, draftKey, draftMode, draftPrompt, proposalId, submitCycle, touched]);

  useEffect(() => {
    if (!draftKey || typeof window === 'undefined') return;
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== draftKey || event.newValue === event.oldValue) return;
      setExternalDraftUpdated(true);
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, [draftKey]);

  const handleResumeDraft = () => {
    if (!draftPrompt) return;
    setFormData(draftPrompt.value.formData);
    setBilling(draftPrompt.value.billing);
    setPendingSigningDocs([]);
    setRestoredSigningDocNames(draftPrompt.value.pendingSigningDocNames);
    setLastSavedAt(draftPrompt.updatedAt);
    setDraftPrompt(null);
    setReattachError(false);
    markTouched();
  };

  const handleDiscardDraft = () => {
    clearProposalDraft(draftKey);
    setDraftPrompt(null);
    setLastSavedAt(null);
    setRestoredSigningDocNames([]);
    setReattachError(false);
  };

  // Fetch entity lists for dropdowns
  const { data: contactsData } = useContacts({ page_size: 100 });
  const { data: companiesData } = useCompanies({ page_size: 100 });

  const contacts = useMemo(() => contactsData?.items ?? [], [contactsData]);
  const companies = useMemo(() => companiesData?.items ?? [], [companiesData]);

  const contactOptions = useMemo(
    () => contacts.map((c) => ({ value: c.id, label: c.full_name })),
    [contacts]
  );
  const companyOptions = useMemo(
    () => companies.map((c) => ({ value: c.id, label: c.name })),
    [companies]
  );

  // The missing-relation confirm-dialog re-fires submit with the same
  // ``ProposalCreate`` payload; ``pendingSigningDocs`` is a sibling on
  // ProposalForm state, so capture the current value here so a deferred
  // confirm still carries the user's chosen signable PDFs.
  const submitPayload = useCallback(
    async (data: ProposalCreate) => {
      submittingRef.current = true;
      setIsSubmitting(true);
      try {
        await onSubmit(data, isCreating ? pendingSigningDocs : []);
        submittedSuccessfullyRef.current = true;
        submittingRef.current = false;
        setIsSubmitting(false);
        clearProposalDraft(draftKey);
        setLastSavedAt(null);
        setTouched(false);
        setAutosaveBlocked(false);
        setRestoredSigningDocNames([]);
        setReattachError(false);
      } catch (err) {
        submittingRef.current = false;
        submittedSuccessfullyRef.current = false;
        setIsSubmitting(false);
        setSubmitCycle((cycle) => cycle + 1);
        throw err;
      }
    },
    [draftKey, isCreating, onSubmit, pendingSigningDocs],
  );

  const missingRelation = useMissingRelationConfirm<ProposalCreate>((data) => {
    void submitPayload(data).catch(() => {
      // Parent submitters own the toast/error text. Keep the local draft.
    });
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (formDisabled) return;
    if (missingRestoredSigningDocNames.length > 0) {
      setReattachError(true);
      return;
    }

    const amountTrimmed = billing.amount.trim();
    const data: ProposalCreate = {
      title: formData.title,
      content: formData.content || null,
      executive_summary: formData.executiveSummary || null,
      scope_of_work: formData.scopeOfWork || null,
      pricing_section: formData.pricingSection || null,
      timeline: formData.timelineField || null,
      terms: formData.terms || null,
      valid_until: formData.validUntil || null,
      status: 'draft',
      contact_id: formData.contactId,
      company_id: formData.companyId,
      payment_type: billing.payment_type,
      recurring_interval: billing.recurring_interval,
      recurring_interval_count: billing.recurring_interval_count,
      amount: amountTrimmed === '' ? null : amountTrimmed,
      currency: billing.currency,
      terms_and_conditions: formData.termsAndConditions.trim() || null,
    };

    // Only nag on create; edit mode pre-selects the proposal's existing
    // relations and the user has already been through this prompt once.
    if (!isEditing && data.contact_id == null && data.company_id == null) {
      missingRelation.request(data);
      return;
    }

    try {
      await submitPayload(data);
    } catch {
      // Parent submitters own the toast/error text. Keep the local draft.
    }
  };

  const handleBillingChange = (next: BillingTermsValue) => {
    setBilling(next);
    markTouched({ discardPrompt: true });
  };

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="space-y-6">
      {userId == null && (
        <p aria-live="polite" className="text-xs text-gray-500 dark:text-gray-400">
          Autosave initializing…
        </p>
      )}
      {autosaveBlocked && (
        <div
          role="alert"
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-700/60 dark:bg-amber-900/20 dark:text-amber-100"
        >
          Your browser blocked local autosave. Keep this page open until you save.
        </div>
      )}
      {externalDraftUpdated && (
        <div
          role="status"
          className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900 dark:border-blue-800/70 dark:bg-blue-900/20 dark:text-blue-100"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>Another tab updated this draft.</span>
            <Button type="button" size="sm" variant="secondary" onClick={() => window.location.reload()}>
              Reload to see latest
            </Button>
          </div>
        </div>
      )}
      {draftPrompt && (
        <div
          role="status"
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-700/60 dark:bg-amber-900/20"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-sm font-semibold text-amber-900 dark:text-amber-100">
                Unsaved {isCreating ? 'proposal' : 'edit'} draft found
              </p>
              <p className="mt-1 text-xs text-amber-800 dark:text-amber-200">
                Saved locally at {formatProposalDraftTime(draftPrompt.updatedAt)}.
                Resume it, or start fresh and remove the saved copy.
              </p>
            </div>
            <div className="flex shrink-0 gap-2">
              <Button type="button" size="sm" onClick={handleResumeDraft}>
                Resume
              </Button>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={handleDiscardDraft}
              >
                Start fresh
              </Button>
            </div>
          </div>
        </div>
      )}
      {!draftPrompt && lastSavedAt && (
        <p aria-live="polite" className="text-xs text-gray-500 dark:text-gray-400">
          Draft saved locally at {formatProposalDraftTime(lastSavedAt)}
        </p>
      )}
      {missingRestoredSigningDocNames.length > 0 && (
        <div
          role={reattachError ? 'alert' : 'status'}
          className={`rounded-lg border px-4 py-3 text-sm ${
            reattachError
              ? 'border-red-200 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-100'
              : 'border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-800/70 dark:bg-blue-900/20 dark:text-blue-100'
          }`}
        >
          Reattach signing document{missingRestoredSigningDocNames.length === 1 ? '' : 's'} before creating this proposal:{' '}
          <span className="font-medium">{missingRestoredSigningDocNames.join(', ')}</span>
        </div>
      )}
      <div className="space-y-4">
        <div>
          <label htmlFor="proposal-title" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Title *
          </label>
          <input
            type="text"
            id="proposal-title"
            name="title"
            required
            autoFocus
            disabled={formDisabled}
            value={formData.title}
            onChange={(e) => updateField('title', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Proposal title..."
          />
        </div>

        <div>
          <label htmlFor="proposal-content" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Content
          </label>
          <textarea
            id="proposal-content"
            name="content"
            rows={3}
            disabled={formDisabled}
            value={formData.content}
            onChange={(e) => updateField('content', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Overall proposal content..."
          />
        </div>

        <div>
          <label htmlFor="proposal-exec-summary" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Executive Summary
          </label>
          <textarea
            id="proposal-exec-summary"
            name="executive_summary"
            rows={3}
            disabled={formDisabled}
            value={formData.executiveSummary}
            onChange={(e) => updateField('executiveSummary', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Executive summary..."
          />
        </div>

        <div>
          <label htmlFor="proposal-scope" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Scope of Work
          </label>
          <textarea
            id="proposal-scope"
            name="scope_of_work"
            rows={3}
            disabled={formDisabled}
            value={formData.scopeOfWork}
            onChange={(e) => updateField('scopeOfWork', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Scope of work details..."
          />
        </div>

        <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-800/40 space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Reference pricing
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              Used in the proposal body for the customer's reference. Billing is
              created manually in the Payments module after the customer signs —
              this never auto-charges.
            </p>
          </div>
          <BillingTermsField
            value={billing}
            onChange={handleBillingChange}
            disabled={formDisabled}
            amountHelpText="Total amount (one-time) or per-period amount (subscription). For display only."
          />
        </div>

        <div>
          <label htmlFor="proposal-pricing" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Pricing Notes
          </label>
          <textarea
            id="proposal-pricing"
            name="pricing_section"
            rows={3}
            disabled={formDisabled}
            value={formData.pricingSection}
            onChange={(e) => updateField('pricingSection', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Additional pricing context shown to the client (line-item breakdowns, assumptions, etc.)"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="proposal-timeline" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Timeline
            </label>
            <textarea
              id="proposal-timeline"
              name="timeline"
              rows={2}
              disabled={formDisabled}
              value={formData.timelineField}
              onChange={(e) => updateField('timelineField', e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
              placeholder="Project timeline..."
            />
          </div>
          <div>
            <label htmlFor="proposal-valid-until" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Valid Until
            </label>
            <input
              type="date"
              id="proposal-valid-until"
              name="valid_until"
              min={isEditing ? undefined : todayDate}
              disabled={formDisabled}
              value={formData.validUntil}
              onChange={(e) => updateField('validUntil', e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
        </div>

        <div>
          <label htmlFor="proposal-terms" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Terms
          </label>
          <textarea
            id="proposal-terms"
            name="terms"
            rows={2}
            disabled={formDisabled}
            value={formData.terms}
            onChange={(e) => updateField('terms', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Terms and conditions..."
          />
        </div>

        <div>
          <label
            htmlFor="proposal-tc-override"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Signing T&amp;C override
          </label>
          <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            Shown inside the customer's Sign-to-Confirm modal. Leave blank to use the
            tenant default (Settings → Branding → Default T&amp;C).
          </p>
          <textarea
            id="proposal-tc-override"
            name="terms_and_conditions"
            rows={4}
            disabled={formDisabled}
            value={formData.termsAndConditions}
            onChange={(e) => updateField('termsAndConditions', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Override the default signing T&Cs for this proposal only..."
          />
        </div>

        {isCreating && (
          <PendingMasterContractField
            value={pendingSigningDocs}
            disabled={formDisabled}
            onChange={(files) => {
              setPendingSigningDocs(files);
              setReattachError(false);
              markTouched({ discardPrompt: true });
            }}
          />
        )}
      </div>

      {/* Related Records */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Related Records</h3>
        {/* Quote relation removed 2026-05-14 — quotes router unmounted. */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <SearchableSelect
            label="Contact"
            id="proposal-contact"
            name="contact_id"
            value={formData.contactId}
            onChange={(val) => updateField('contactId', val)}
            options={contactOptions}
            placeholder="Search contacts..."
            disabled={formDisabled}
          />
          <SearchableSelect
            label="Company"
            id="proposal-company"
            name="company_id"
            value={formData.companyId}
            onChange={(val) => updateField('companyId', val)}
            options={companyOptions}
            placeholder="Search companies..."
            disabled={formDisabled}
          />
        </div>
      </div>

      {/* Actions */}
      <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        {signingUploadStatus && (
          <p
            aria-live="polite"
            className="text-xs text-gray-600 dark:text-gray-300 sm:mr-auto"
          >
            Uploading signing document {signingUploadStatus.current} of{' '}
            {signingUploadStatus.total}: <span className="font-medium">{signingUploadStatus.fileName}</span>
          </p>
        )}
        <Button
          type="button"
          variant="secondary"
          onClick={onCancel}
          disabled={formDisabled}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          disabled={!formData.title.trim() || formDisabled}
          isLoading={formDisabled}
        >
          {signingUploadStatus
            ? `Uploading ${signingUploadStatus.current}/${signingUploadStatus.total}…`
            : isEditing
              ? 'Save'
              : 'Create Proposal'}
        </Button>
      </div>
      <MissingRelationDialog
        isOpen={missingRelation.isOpen}
        onCancel={missingRelation.onCancel}
        onConfirm={missingRelation.onConfirm}
        isLoading={formDisabled}
      />
    </form>
  );
}

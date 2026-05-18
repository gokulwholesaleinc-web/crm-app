import { useEffect, useState, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { Button } from '../../../components/ui';
import { FormInput, FormSelect, FormTextarea } from '../../../components/forms';
import { useLeadSources, useLeadPipelineStages } from '../../../hooks/useLeads';
import { useUnsavedChangesWarning } from '../../../hooks/useUnsavedChangesWarning';
import { normalizeEmail, normalizePhone } from '../../../utils/inputNormalize';
import { useFormSubmitShortcut } from '../../../hooks/useSubmitShortcut';
import type { PipelineStage } from '../../../types';

export interface LeadFormData {
  firstName?: string;
  lastName?: string;
  email?: string;
  phone?: string;
  company?: string;
  jobTitle?: string;
  source_id?: number | null;
  pipeline_stage_id?: number | null;
  status: string;
  salesCode?: string;
  notes?: string;
}

export interface LeadFormProps {
  initialData?: Partial<LeadFormData>;
  onSubmit: (data: LeadFormData) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
  submitLabel?: string;
  score?: number | null;
  // When true (create mode), hide everything below email/phone until at
  // least one contact field has a value. Edit mode passes false so users
  // can keep working on partial historical rows.
  requireContactFirst?: boolean;
  onDirtyChange?: (isDirty: boolean) => void;
}

// `converted` is intentionally absent — the only legitimate way to land
// in that state is through the Convert flow on the lead detail page,
// which creates the Contact (and optional Company). Picking it here would 400.
const leadStatuses = [
  { value: 'new', label: 'New' },
  { value: 'contacted', label: 'Contacted' },
  { value: 'qualified', label: 'Qualified' },
  { value: 'unqualified', label: 'Unqualified' },
  { value: 'lost', label: 'Lost' },
];

export function LeadForm({
  initialData,
  onSubmit,
  onCancel,
  isLoading = false,
  submitLabel = 'Save Lead',
  score = null,
  requireContactFirst = false,
  onDirtyChange,
}: LeadFormProps) {
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors, isDirty },
  } = useForm<LeadFormData>({
    defaultValues: {
      firstName: '',
      lastName: '',
      email: '',
      phone: '',
      company: '',
      jobTitle: '',
      status: 'new',
      salesCode: '',
      notes: '',
      ...initialData,
    },
  });

  const [sourceId, setSourceId] = useState<number | null>(initialData?.source_id ?? null);
  const [pipelineStageId, setPipelineStageId] = useState<number | null>(initialData?.pipeline_stage_id ?? null);

  const sidecarChanged =
    sourceId !== (initialData?.source_id ?? null) ||
    pipelineStageId !== (initialData?.pipeline_stage_id ?? null);
  const hasUnsavedChanges = isDirty || sidecarChanged;
  useUnsavedChangesWarning(hasUnsavedChanges);

  useEffect(() => {
    onDirtyChange?.(hasUnsavedChanges);
  }, [hasUnsavedChanges, onDirtyChange]);

  const { data: leadSourcesData } = useLeadSources();
  const { data: pipelineStagesData } = useLeadPipelineStages();

  const sourceOptions = useMemo(
    () => [
      { value: '', label: '— Select source —' },
      ...(leadSourcesData ?? []).map((s: { id: number; name: string }) => ({
        value: String(s.id),
        label: s.name,
      })),
    ],
    [leadSourcesData]
  );

  // Terminal stages (Won/Lost) are excluded from the form-level
  // dropdown. The natural way to land in Won is to drag the card onto
  // the Won column on /pipeline (which runs the auto-Contact-creation
  // side effects); Lost is set from the detail page. Keeping them out
  // of this dropdown avoids accidental transitions during a routine edit.
  const pipelineStageOptions = useMemo(
    () => [
      { value: '', label: '(unstaged)' },
      ...((pipelineStagesData ?? []) as PipelineStage[])
        .filter((s) => s.is_active && !s.is_won && !s.is_lost)
        .map((s) => ({
          value: String(s.id),
          label: s.name,
        })),
    ],
    [pipelineStagesData]
  );

  const [formError, setFormError] = useState<string | null>(null);
  const formRef = useFormSubmitShortcut();

  const watchedEmail = watch('email') ?? '';
  const watchedPhone = watch('phone') ?? '';
  const hasContact = !!(watchedEmail.trim() || watchedPhone.trim());
  const showFullForm = !requireContactFirst || hasContact;

  const onFormSubmit = (data: LeadFormData) => {
    if (requireContactFirst && !data.email?.trim() && !data.phone?.trim()) {
      setFormError('Enter an email or phone before saving.');
      return;
    }
    const hasName = !!(data.firstName?.trim() || data.lastName?.trim());
    const hasCompany = !!data.company?.trim();
    if (!hasName && !hasCompany) {
      setFormError('Either a name or company name is required.');
      return;
    }
    setFormError(null);
    return onSubmit({
      ...data,
      source_id: sourceId,
      pipeline_stage_id: pipelineStageId,
    });
  };

  return (
    <form ref={formRef} onSubmit={handleSubmit(onFormSubmit)} className="space-y-8">
      {formError && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-3" aria-live="polite">
          <p className="text-sm text-red-700 dark:text-red-400">{formError}</p>
        </div>
      )}

      <section>
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-1">
          Contact
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {requireContactFirst
            ? 'Enter an email or phone to continue.'
            : 'Either an email or phone is recommended so the lead is reachable.'}
        </p>
        <div className="grid grid-cols-1 gap-x-4 gap-y-5 sm:grid-cols-2">
          <FormInput
            label="Email"
            name="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            spellCheck={false}
            register={register('email', {
              pattern: {
                value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i,
                message: 'Invalid email address',
              },
            })}
            error={errors.email?.message}
            onBlur={(e) =>
              setValue('email', normalizeEmail(e.target.value), { shouldDirty: true })
            }
            onPaste={(e) => {
              e.preventDefault();
              setValue('email', normalizeEmail(e.clipboardData.getData('text')), {
                shouldDirty: true,
              });
            }}
          />

          <FormInput
            label="Phone"
            name="phone"
            type="tel"
            autoComplete="tel"
            inputMode="tel"
            register={register('phone')}
            onBlur={(e) =>
              setValue('phone', normalizePhone(e.target.value), { shouldDirty: true })
            }
            onPaste={(e) => {
              e.preventDefault();
              setValue('phone', normalizePhone(e.clipboardData.getData('text')), {
                shouldDirty: true,
              });
            }}
          />
        </div>
      </section>

      {!showFullForm && (
        <div
          className="rounded-md border border-dashed border-gray-300 dark:border-gray-600 p-6 text-center"
          aria-live="polite"
        >
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Add an email or phone above to fill in the rest of the lead.
          </p>
        </div>
      )}

      <section className={showFullForm ? '' : 'hidden'} aria-hidden={!showFullForm}>
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Basic Information
        </h3>
        <div className="grid grid-cols-1 gap-x-4 gap-y-5 sm:grid-cols-2">
          <FormInput
            label="First Name"
            name="firstName"
            autoComplete="given-name"
            register={register('firstName')}
            error={errors.firstName?.message}
          />

          <FormInput
            label="Last Name"
            name="lastName"
            autoComplete="family-name"
            register={register('lastName')}
            error={errors.lastName?.message}
          />

          <FormInput
            label="Company Name"
            name="company"
            autoComplete="organization"
            register={register('company')}
            placeholder="Enter company name..."
          />
          <FormInput
            label="Job Title"
            name="jobTitle"
            autoComplete="organization-title"
            register={register('jobTitle')}
          />
        </div>
      </section>

      <section className={showFullForm ? '' : 'hidden'} aria-hidden={!showFullForm}>
        <div className="flex items-baseline justify-between mb-4">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
            Lead Information
          </h3>
          {score != null && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Score <span className="font-semibold text-gray-700 dark:text-gray-200">{score}</span>/100 · auto-calculated
            </span>
          )}
        </div>
        <div className="grid grid-cols-1 gap-x-4 gap-y-5 sm:grid-cols-2">
          <FormSelect
            label="Source"
            name="source_id"
            options={sourceOptions}
            value={sourceId == null ? '' : String(sourceId)}
            onChange={(e) => {
              const v = e.target.value;
              setSourceId(v === '' ? null : Number(v));
            }}
          />

          <FormSelect
            label="Status"
            name="status"
            options={leadStatuses}
            required
            register={register('status', {
              required: 'Status is required',
            })}
            error={errors.status?.message}
          />

          <FormSelect
            label="Pipeline Stage"
            name="pipeline_stage_id"
            options={pipelineStageOptions}
            value={pipelineStageId == null ? '' : String(pipelineStageId)}
            onChange={(e) => {
              const v = e.target.value;
              setPipelineStageId(v === '' ? null : Number(v));
            }}
          />

          <FormInput
            label="Sales Code"
            name="salesCode"
            register={register('salesCode')}
            placeholder="Optional"
          />
        </div>
      </section>

      <section className={showFullForm ? '' : 'hidden'} aria-hidden={!showFullForm}>
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Notes
        </h3>
        <FormTextarea
          label="Notes"
          name="notes"
          rows={4}
          placeholder="Add any additional notes about this lead..."
          register={register('notes')}
        />
      </section>

      <div className="flex justify-end gap-3 pt-2 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" isLoading={isLoading} disabled={!showFullForm}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

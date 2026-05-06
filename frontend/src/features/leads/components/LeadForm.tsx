import { useState, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { Button, SearchableSelect } from '../../../components/ui';
import { FormInput, FormSelect, FormTextarea } from '../../../components/forms';
import { useCompanies } from '../../../hooks/useCompanies';
import { useLeadSources, useLeadPipelineStages } from '../../../hooks/useLeads';
import { useUnsavedChangesWarning } from '../../../hooks/useUnsavedChangesWarning';

export interface LeadFormData {
  firstName?: string;
  lastName?: string;
  email?: string;
  phone?: string;
  company?: string;
  jobTitle?: string;
  source: string;
  source_id?: number | null;
  company_id?: number | null;
  pipeline_stage_id?: number | null;
  status: string;
  score?: number;
  salesCode?: string;
  notes?: string;
}

export interface LeadFormProps {
  initialData?: Partial<LeadFormData>;
  onSubmit: (data: LeadFormData) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
  submitLabel?: string;
}

// `converted` is intentionally absent — the only legitimate way to land
// in that state is through the Convert flow on the lead detail page,
// which creates the Contact + Opportunity. Picking it here would 400.
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
}: LeadFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors, isDirty },
  } = useForm<LeadFormData>({
    defaultValues: {
      firstName: '',
      lastName: '',
      email: '',
      phone: '',
      company: '',
      jobTitle: '',
      source: 'website',
      status: 'new',
      score: 0,
      salesCode: '',
      notes: '',
      ...initialData,
    },
  });

  const [sourceId, setSourceId] = useState<number | null>(initialData?.source_id ?? null);
  const [companyId, setCompanyId] = useState<number | null>(initialData?.company_id ?? null);
  const [pipelineStageId, setPipelineStageId] = useState<number | null>(initialData?.pipeline_stage_id ?? null);

  const sidecarChanged =
    sourceId !== (initialData?.source_id ?? null) ||
    companyId !== (initialData?.company_id ?? null) ||
    pipelineStageId !== (initialData?.pipeline_stage_id ?? null);
  useUnsavedChangesWarning(isDirty || sidecarChanged);

  const { data: leadSourcesData } = useLeadSources();
  const { data: companiesData } = useCompanies({ page_size: 100 });
  const { data: pipelineStagesData } = useLeadPipelineStages();

  const sourceOptions = useMemo(
    () => (leadSourcesData ?? []).map((s: { id: number; name: string }) => ({ value: s.id, label: s.name })),
    [leadSourcesData]
  );

  const companyOptions = useMemo(
    () => (companiesData?.items ?? []).map((c) => ({ value: c.id, label: c.name })),
    [companiesData]
  );

  const pipelineStageOptions = useMemo(
    () => (pipelineStagesData ?? []).map((s: { id: number; name: string }) => ({ value: s.id, label: s.name })),
    [pipelineStagesData]
  );

  const [formError, setFormError] = useState<string | null>(null);

  const onFormSubmit = (data: LeadFormData) => {
    const hasName = !!(data.firstName?.trim() || data.lastName?.trim());
    const hasCompany = !!data.company?.trim();
    if (!hasName && !hasCompany) {
      setFormError('Either a name or company name is required.');
      return;
    }
    setFormError(null);
    return onSubmit({ ...data, source_id: sourceId, company_id: companyId, pipeline_stage_id: pipelineStageId });
  };

  return (
    <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-6">
      {formError && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4" aria-live="polite">
          <p className="text-sm text-red-700 dark:text-red-400">{formError}</p>
        </div>
      )}
      {/* Basic Information */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">
          Basic Information
        </h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
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
          />

          <FormInput
            label="Phone"
            name="phone"
            type="tel"
            autoComplete="tel"
            inputMode="tel"
            register={register('phone')}
          />
        </div>
      </div>

      {/* Work Information */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">
          Work Information
        </h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <FormInput
            label="Company Name"
            name="company"
            autoComplete="organization"
            register={register('company')}
            placeholder="Enter company name..."
          />

          <SearchableSelect
            label="Link to Existing Company"
            id="lead-company"
            name="company_id"
            value={companyId}
            onChange={setCompanyId}
            options={companyOptions}
            placeholder="Search companies..."
          />

          <FormInput
            label="Job Title"
            name="jobTitle"
            autoComplete="organization-title"
            register={register('jobTitle')}
          />
        </div>
      </div>

      {/* Lead Information */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">
          Lead Information
        </h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          <SearchableSelect
            label="Source"
            id="lead-source"
            name="source_id"
            value={sourceId}
            onChange={setSourceId}
            options={sourceOptions}
            placeholder="Search sources..."
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

          <SearchableSelect
            label="Pipeline Stage"
            id="lead-pipeline-stage"
            name="pipeline_stage_id"
            value={pipelineStageId}
            onChange={setPipelineStageId}
            options={pipelineStageOptions}
            placeholder="Select pipeline stage..."
          />

          <FormInput
            label="Sales Code"
            name="salesCode"
            register={register('salesCode')}
            placeholder="Enter sales code..."
          />

          <FormInput
            label="Lead Score (0-100)"
            name="score"
            type="number"
            min={0}
            max={100}
            register={register('score', {
              min: { value: 0, message: 'Score must be at least 0' },
              max: { value: 100, message: 'Score cannot exceed 100' },
            })}
            error={errors.score?.message}
          />
        </div>
      </div>

      {/* Notes */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">Notes</h3>
        <FormTextarea
          label="Notes"
          name="notes"
          rows={4}
          placeholder="Add any additional notes about this lead..."
          register={register('notes')}
        />
      </div>

      {/* Form Actions */}
      <div className="flex justify-end space-x-3">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" isLoading={isLoading}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

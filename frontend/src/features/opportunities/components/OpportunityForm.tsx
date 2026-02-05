import { useForm } from 'react-hook-form';
import { Button } from '../../../components/ui/Button';
import { FormInput, FormSelect, FormTextarea } from '../../../components/forms';

export interface OpportunityFormData {
  name: string;
  value: number;
  stage: string;
  probability?: number;
  expectedCloseDate?: string;
  contactId?: string;
  companyId?: string;
  description?: string;
  notes?: string;
}

export interface OpportunityFormProps {
  initialData?: Partial<OpportunityFormData>;
  onSubmit: (data: OpportunityFormData) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
  submitLabel?: string;
  contacts?: Array<{ id: string; name: string }>;
  companies?: Array<{ id: string; name: string }>;
}

const opportunityStages = [
  { value: 'qualification', label: 'Qualification', probability: 20 },
  { value: 'needs_analysis', label: 'Needs Analysis', probability: 40 },
  { value: 'proposal', label: 'Proposal', probability: 60 },
  { value: 'negotiation', label: 'Negotiation', probability: 80 },
  { value: 'closed_won', label: 'Closed Won', probability: 100 },
  { value: 'closed_lost', label: 'Closed Lost', probability: 0 },
];

export function OpportunityForm({
  initialData,
  onSubmit,
  onCancel,
  isLoading = false,
  submitLabel = 'Save Opportunity',
  contacts = [],
  companies = [],
}: OpportunityFormProps) {
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<OpportunityFormData>({
    defaultValues: {
      name: '',
      value: 0,
      stage: 'qualification',
      probability: 20,
      expectedCloseDate: '',
      contactId: '',
      companyId: '',
      description: '',
      notes: '',
      ...initialData,
    },
  });

  const selectedStage = watch('stage');

  // Update probability when stage changes
  const handleStageChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const stage = e.target.value;
    const stageInfo = opportunityStages.find((s) => s.value === stage);
    if (stageInfo) {
      setValue('probability', stageInfo.probability);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      {/* Basic Information */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">
          Opportunity Details
        </h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <FormInput
              label="Opportunity Name"
              name="name"
              required
              placeholder="e.g., Acme Corp - Enterprise License"
              register={register('name', {
                required: 'Opportunity name is required',
              })}
              error={errors.name?.message}
            />
          </div>

          <FormInput
            label="Value"
            name="value"
            type="number"
            required
            placeholder="0.00"
            register={register('value', {
              required: 'Value is required',
              min: { value: 0, message: 'Value must be positive' },
            })}
            error={errors.value?.message}
          />

          <FormInput
            label="Expected Close Date"
            name="expectedCloseDate"
            type="date"
            register={register('expectedCloseDate')}
          />
        </div>
      </div>

      {/* Pipeline Stage */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Pipeline Stage</h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <FormSelect
            label="Stage"
            name="stage"
            required
            options={opportunityStages.map(s => ({ value: s.value, label: s.label }))}
            register={register('stage', {
              required: 'Stage is required',
              onChange: handleStageChange,
            })}
            error={errors.stage?.message}
          />

          <FormInput
            label="Win Probability (%)"
            name="probability"
            type="number"
            min={0}
            max={100}
            register={register('probability', {
              min: { value: 0, message: 'Probability must be at least 0' },
              max: { value: 100, message: 'Probability cannot exceed 100' },
            })}
            error={errors.probability?.message}
          />
        </div>

        {/* Visual Stage Indicator */}
        <div className="mt-6">
          <div className="flex items-center justify-between">
            {opportunityStages
              .filter((s) => s.value !== 'closed_lost')
              .map((stage, index) => (
                <div
                  key={stage.value}
                  className={`flex-1 ${index > 0 ? 'ml-2' : ''}`}
                >
                  <div
                    className={`h-2 rounded-full ${
                      selectedStage === stage.value
                        ? 'bg-primary-500'
                        : opportunityStages.findIndex(
                            (s) => s.value === selectedStage
                          ) > index
                        ? 'bg-primary-300'
                        : 'bg-gray-200'
                    }`}
                  />
                  <p className="mt-1 text-xs text-gray-500 text-center truncate">
                    {stage.label}
                  </p>
                </div>
              ))}
          </div>
        </div>
      </div>

      {/* Related Records */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">
          Related Records
        </h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <FormSelect
            label="Primary Contact"
            name="contactId"
            placeholder="Select a contact"
            options={contacts.map((contact) => ({ value: contact.id, label: contact.name }))}
            register={register('contactId')}
          />

          <FormSelect
            label="Company"
            name="companyId"
            placeholder="Select a company"
            options={companies.map((company) => ({ value: company.id, label: company.name }))}
            register={register('companyId')}
          />
        </div>
      </div>

      {/* Description & Notes */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">
          Description & Notes
        </h3>
        <div className="space-y-4">
          <FormTextarea
            label="Description"
            name="description"
            rows={3}
            placeholder="Describe the opportunity..."
            register={register('description')}
          />

          <FormTextarea
            label="Internal Notes"
            name="notes"
            rows={3}
            placeholder="Add any internal notes..."
            register={register('notes')}
          />
        </div>
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

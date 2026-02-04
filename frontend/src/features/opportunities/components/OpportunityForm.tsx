import { useForm } from 'react-hook-form';
import { Button } from '../../../components/ui/Button';

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
            <label
              htmlFor="name"
              className="block text-sm font-medium text-gray-700"
            >
              Opportunity Name *
            </label>
            <input
              type="text"
              id="name"
              {...register('name', {
                required: 'Opportunity name is required',
              })}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
              placeholder="e.g., Acme Corp - Enterprise License"
            />
            {errors.name && (
              <p className="mt-1 text-sm text-red-600">{errors.name.message}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="value"
              className="block text-sm font-medium text-gray-700"
            >
              Value *
            </label>
            <div className="mt-1 relative rounded-md shadow-sm">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <span className="text-gray-500 sm:text-sm">$</span>
              </div>
              <input
                type="number"
                id="value"
                {...register('value', {
                  required: 'Value is required',
                  min: { value: 0, message: 'Value must be positive' },
                })}
                className="pl-7 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                placeholder="0.00"
              />
            </div>
            {errors.value && (
              <p className="mt-1 text-sm text-red-600">{errors.value.message}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="expectedCloseDate"
              className="block text-sm font-medium text-gray-700"
            >
              Expected Close Date
            </label>
            <input
              type="date"
              id="expectedCloseDate"
              {...register('expectedCloseDate')}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            />
          </div>
        </div>
      </div>

      {/* Pipeline Stage */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Pipeline Stage</h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <div>
            <label
              htmlFor="stage"
              className="block text-sm font-medium text-gray-700"
            >
              Stage *
            </label>
            <select
              id="stage"
              {...register('stage', {
                required: 'Stage is required',
              })}
              onChange={(e) => {
                register('stage').onChange(e);
                handleStageChange(e);
              }}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            >
              {opportunityStages.map((stage) => (
                <option key={stage.value} value={stage.value}>
                  {stage.label}
                </option>
              ))}
            </select>
            {errors.stage && (
              <p className="mt-1 text-sm text-red-600">{errors.stage.message}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="probability"
              className="block text-sm font-medium text-gray-700"
            >
              Win Probability (%)
            </label>
            <input
              type="number"
              id="probability"
              min="0"
              max="100"
              {...register('probability', {
                min: { value: 0, message: 'Probability must be at least 0' },
                max: { value: 100, message: 'Probability cannot exceed 100' },
              })}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            />
            {errors.probability && (
              <p className="mt-1 text-sm text-red-600">
                {errors.probability.message}
              </p>
            )}
          </div>
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
          <div>
            <label
              htmlFor="contactId"
              className="block text-sm font-medium text-gray-700"
            >
              Primary Contact
            </label>
            <select
              id="contactId"
              {...register('contactId')}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            >
              <option value="">Select a contact</option>
              {contacts.map((contact) => (
                <option key={contact.id} value={contact.id}>
                  {contact.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              htmlFor="companyId"
              className="block text-sm font-medium text-gray-700"
            >
              Company
            </label>
            <select
              id="companyId"
              {...register('companyId')}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            >
              <option value="">Select a company</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Description & Notes */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">
          Description & Notes
        </h3>
        <div className="space-y-4">
          <div>
            <label
              htmlFor="description"
              className="block text-sm font-medium text-gray-700"
            >
              Description
            </label>
            <textarea
              id="description"
              rows={3}
              {...register('description')}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
              placeholder="Describe the opportunity..."
            />
          </div>

          <div>
            <label
              htmlFor="notes"
              className="block text-sm font-medium text-gray-700"
            >
              Internal Notes
            </label>
            <textarea
              id="notes"
              rows={3}
              {...register('notes')}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
              placeholder="Add any internal notes..."
            />
          </div>
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

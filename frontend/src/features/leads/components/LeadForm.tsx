import { useForm } from 'react-hook-form';
import { Button } from '../../../components/ui/Button';
import { FormInput, FormSelect, FormTextarea } from '../../../components/forms';

export interface LeadFormData {
  firstName: string;
  lastName: string;
  email: string;
  phone?: string;
  company?: string;
  jobTitle?: string;
  source: string;
  status: string;
  score?: number;
  notes?: string;
}

export interface LeadFormProps {
  initialData?: Partial<LeadFormData>;
  onSubmit: (data: LeadFormData) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
  submitLabel?: string;
}

const leadSources = [
  { value: 'website', label: 'Website' },
  { value: 'referral', label: 'Referral' },
  { value: 'social_media', label: 'Social Media' },
  { value: 'email_campaign', label: 'Email Campaign' },
  { value: 'cold_call', label: 'Cold Call' },
  { value: 'trade_show', label: 'Trade Show' },
  { value: 'other', label: 'Other' },
];

const leadStatuses = [
  { value: 'new', label: 'New' },
  { value: 'contacted', label: 'Contacted' },
  { value: 'qualified', label: 'Qualified' },
  { value: 'unqualified', label: 'Unqualified' },
  { value: 'nurturing', label: 'Nurturing' },
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
    formState: { errors },
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
      notes: '',
      ...initialData,
    },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      {/* Basic Information */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">
          Basic Information
        </h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <FormInput
            label="First Name"
            name="firstName"
            required
            register={register('firstName', {
              required: 'First name is required',
            })}
            error={errors.firstName?.message}
          />

          <FormInput
            label="Last Name"
            name="lastName"
            required
            register={register('lastName', {
              required: 'Last name is required',
            })}
            error={errors.lastName?.message}
          />

          <FormInput
            label="Email"
            name="email"
            type="email"
            required
            register={register('email', {
              required: 'Email is required',
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
            register={register('phone')}
          />
        </div>
      </div>

      {/* Work Information */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">
          Work Information
        </h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <FormInput
            label="Company"
            name="company"
            register={register('company')}
          />

          <FormInput
            label="Job Title"
            name="jobTitle"
            register={register('jobTitle')}
          />
        </div>
      </div>

      {/* Lead Information */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">
          Lead Information
        </h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          <FormSelect
            label="Source"
            name="source"
            options={leadSources}
            required
            register={register('source', {
              required: 'Source is required',
            })}
            error={errors.source?.message}
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
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Notes</h3>
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

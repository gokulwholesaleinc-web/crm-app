import { useForm } from 'react-hook-form';
import { Button } from '../../../components/ui/Button';

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
          <div>
            <label
              htmlFor="firstName"
              className="block text-sm font-medium text-gray-700"
            >
              First Name *
            </label>
            <input
              type="text"
              id="firstName"
              {...register('firstName', {
                required: 'First name is required',
              })}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            />
            {errors.firstName && (
              <p className="mt-1 text-sm text-red-600">
                {errors.firstName.message}
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="lastName"
              className="block text-sm font-medium text-gray-700"
            >
              Last Name *
            </label>
            <input
              type="text"
              id="lastName"
              {...register('lastName', {
                required: 'Last name is required',
              })}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            />
            {errors.lastName && (
              <p className="mt-1 text-sm text-red-600">
                {errors.lastName.message}
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-gray-700"
            >
              Email *
            </label>
            <input
              type="email"
              id="email"
              {...register('email', {
                required: 'Email is required',
                pattern: {
                  value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i,
                  message: 'Invalid email address',
                },
              })}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            />
            {errors.email && (
              <p className="mt-1 text-sm text-red-600">{errors.email.message}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="phone"
              className="block text-sm font-medium text-gray-700"
            >
              Phone
            </label>
            <input
              type="tel"
              id="phone"
              {...register('phone')}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            />
          </div>
        </div>
      </div>

      {/* Work Information */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">
          Work Information
        </h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <div>
            <label
              htmlFor="company"
              className="block text-sm font-medium text-gray-700"
            >
              Company
            </label>
            <input
              type="text"
              id="company"
              {...register('company')}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            />
          </div>

          <div>
            <label
              htmlFor="jobTitle"
              className="block text-sm font-medium text-gray-700"
            >
              Job Title
            </label>
            <input
              type="text"
              id="jobTitle"
              {...register('jobTitle')}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            />
          </div>
        </div>
      </div>

      {/* Lead Information */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">
          Lead Information
        </h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          <div>
            <label
              htmlFor="source"
              className="block text-sm font-medium text-gray-700"
            >
              Source *
            </label>
            <select
              id="source"
              {...register('source', {
                required: 'Source is required',
              })}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            >
              {leadSources.map((source) => (
                <option key={source.value} value={source.value}>
                  {source.label}
                </option>
              ))}
            </select>
            {errors.source && (
              <p className="mt-1 text-sm text-red-600">{errors.source.message}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="status"
              className="block text-sm font-medium text-gray-700"
            >
              Status *
            </label>
            <select
              id="status"
              {...register('status', {
                required: 'Status is required',
              })}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            >
              {leadStatuses.map((status) => (
                <option key={status.value} value={status.value}>
                  {status.label}
                </option>
              ))}
            </select>
            {errors.status && (
              <p className="mt-1 text-sm text-red-600">{errors.status.message}</p>
            )}
          </div>

          <div>
            <label
              htmlFor="score"
              className="block text-sm font-medium text-gray-700"
            >
              Lead Score (0-100)
            </label>
            <input
              type="number"
              id="score"
              min="0"
              max="100"
              {...register('score', {
                min: { value: 0, message: 'Score must be at least 0' },
                max: { value: 100, message: 'Score cannot exceed 100' },
              })}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            />
            {errors.score && (
              <p className="mt-1 text-sm text-red-600">{errors.score.message}</p>
            )}
          </div>
        </div>
      </div>

      {/* Notes */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Notes</h3>
        <div>
          <textarea
            id="notes"
            rows={4}
            {...register('notes')}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            placeholder="Add any additional notes about this lead..."
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

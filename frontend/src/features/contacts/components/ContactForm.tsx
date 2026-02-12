import { useState, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { Button, SearchableSelect } from '../../../components/ui';
import { FormInput, FormTextarea } from '../../../components/forms';
import { useCompanies } from '../../../hooks/useCompanies';

export interface ContactFormData {
  firstName: string;
  lastName: string;
  email: string;
  phone?: string;
  company_id?: number | null;
  jobTitle?: string;
  address?: string;
  city?: string;
  state?: string;
  zipCode?: string;
  country?: string;
  notes?: string;
  tags?: string[];
}

export interface ContactFormProps {
  initialData?: Partial<ContactFormData>;
  onSubmit: (data: ContactFormData) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
  submitLabel?: string;
}

export function ContactForm({
  initialData,
  onSubmit,
  onCancel,
  isLoading = false,
  submitLabel = 'Save Contact',
}: ContactFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ContactFormData>({
    defaultValues: {
      firstName: '',
      lastName: '',
      email: '',
      phone: '',
      jobTitle: '',
      address: '',
      city: '',
      state: '',
      zipCode: '',
      country: '',
      notes: '',
      ...initialData,
    },
  });

  const [companyId, setCompanyId] = useState<number | null>(initialData?.company_id ?? null);
  const { data: companiesData } = useCompanies({ page_size: 100 });

  const companyOptions = useMemo(
    () => (companiesData?.items ?? []).map((c) => ({ value: c.id, label: c.name })),
    [companiesData]
  );

  const onFormSubmit = (data: ContactFormData) => {
    return onSubmit({ ...data, company_id: companyId });
  };

  return (
    <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-6">
      {/* Basic Information */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">
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
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">
          Work Information
        </h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <SearchableSelect
            label="Company"
            id="contact-company"
            name="company_id"
            value={companyId}
            onChange={setCompanyId}
            options={companyOptions}
            placeholder="Search companies..."
          />

          <FormInput
            label="Job Title"
            name="jobTitle"
            register={register('jobTitle')}
          />
        </div>
      </div>

      {/* Address Information */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">Address</h3>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <FormInput
              label="Street Address"
              name="address"
              register={register('address')}
            />
          </div>

          <FormInput
            label="City"
            name="city"
            register={register('city')}
          />

          <FormInput
            label="State / Province"
            name="state"
            register={register('state')}
          />

          <FormInput
            label="ZIP / Postal Code"
            name="zipCode"
            register={register('zipCode')}
          />

          <FormInput
            label="Country"
            name="country"
            register={register('country')}
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
          placeholder="Add any additional notes about this contact..."
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

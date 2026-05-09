import { useState, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { Button, SearchableSelect } from '../../../components/ui';
import { FormInput, FormTextarea } from '../../../components/forms';
import { useCompanies } from '../../../hooks/useCompanies';
import { useUnsavedChangesWarning } from '../../../hooks/useUnsavedChangesWarning';
import { normalizeEmail, normalizePhone } from '../../../utils/inputNormalize';
import type { ContactFormData } from './contactFormHelpers';

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
    setValue,
    formState: { errors, isDirty },
  } = useForm<ContactFormData>({
    defaultValues: {
      firstName: '',
      lastName: '',
      email: '',
      phone: '',
      jobTitle: '',
      salesCode: '',
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
  const companyChanged = companyId !== (initialData?.company_id ?? null);
  useUnsavedChangesWarning(isDirty || companyChanged);

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
            autoComplete="given-name"
            register={register('firstName', {
              required: 'First name is required',
            })}
            error={errors.firstName?.message}
          />

          <FormInput
            label="Last Name"
            name="lastName"
            required
            autoComplete="family-name"
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
            autoComplete="email"
            inputMode="email"
            spellCheck={false}
            register={register('email', {
              required: 'Email is required',
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
            autoComplete="organization-title"
            register={register('jobTitle')}
          />

          <FormInput
            label="Sales Code"
            name="salesCode"
            register={register('salesCode')}
            placeholder="Enter sales code..."
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
              autoComplete="street-address"
              register={register('address')}
            />
          </div>

          <FormInput
            label="City"
            name="city"
            autoComplete="address-level2"
            register={register('city')}
          />

          <FormInput
            label="State / Province"
            name="state"
            autoComplete="address-level1"
            register={register('state')}
          />

          <FormInput
            label="ZIP / Postal Code"
            name="zipCode"
            autoComplete="postal-code"
            register={register('zipCode')}
          />

          <FormInput
            label="Country"
            name="country"
            autoComplete="country-name"
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

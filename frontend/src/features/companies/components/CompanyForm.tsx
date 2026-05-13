/**
 * Company form for creating/editing companies
 */

import { useEffect, useMemo } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { Select } from '../../../components/ui/Select';
import { FormTextarea } from '../../../components/forms';
import { useUnsavedChangesWarning } from '../../../hooks/useUnsavedChangesWarning';
import { useUsers } from '../../../hooks/useAuth';
import { normalizeEmail, normalizePhone } from '../../../utils/inputNormalize';
import type { Company, CompanyCreate, CompanyUpdate } from '../../../types';
import { useFormSubmitShortcut } from '../../../hooks/useSubmitShortcut';
import { parseLooseInt } from './companyFormHelpers';

interface CompanyFormProps {
  company?: Company;
  onSubmit: (data: CompanyCreate | CompanyUpdate) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
}

interface FormValues {
  name: string;
  website: string;
  industry: string;
  company_size: string;
  phone: string;
  email: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  annual_revenue: string;
  employee_count: string;
  linkedin_url: string;
  twitter_handle: string;
  description: string;
  link_creative_tier: string;
  sow_url: string;
  account_manager: string;
  status: string;
  segment: string;
  owner_id: string;
}

const statusOptions = [
  { value: 'prospect', label: 'Prospect' },
  { value: 'customer', label: 'Customer' },
  { value: 'churned', label: 'Churned' },
];

const companySizeOptions = [
  { value: '', label: 'Select size...' },
  { value: '1-10', label: '1-10 employees' },
  { value: '11-50', label: '11-50 employees' },
  { value: '51-200', label: '51-200 employees' },
  { value: '201-500', label: '201-500 employees' },
  { value: '501-1000', label: '501-1000 employees' },
  { value: '1001-5000', label: '1001-5000 employees' },
  { value: '5001+', label: '5001+ employees' },
];

const industryOptions = [
  { value: '', label: 'Select industry...' },
  { value: 'technology', label: 'Technology' },
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'finance', label: 'Finance' },
  { value: 'manufacturing', label: 'Manufacturing' },
  { value: 'retail', label: 'Retail' },
  { value: 'education', label: 'Education' },
  { value: 'real_estate', label: 'Real Estate' },
  { value: 'consulting', label: 'Consulting' },
  { value: 'media', label: 'Media & Entertainment' },
  { value: 'other', label: 'Other' },
];

const linkCreativeTierOptions = [
  { value: '', label: 'Select tier...' },
  { value: '1', label: 'Tier 1' },
  { value: '2', label: 'Tier 2' },
  { value: '3', label: 'Tier 3' },
  { value: '4', label: 'Tier 4' },
  { value: '5', label: 'Tier 5' },
];

const segmentOptions = [
  { value: '', label: 'Select segment...' },
  { value: 'retail', label: 'Retail' },
  { value: 'food_producer', label: 'Food Producer' },
  { value: 'technology', label: 'Technology' },
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'education', label: 'Education' },
  { value: 'manufacturing', label: 'Manufacturing' },
  { value: 'other', label: 'Other' },
];

export function CompanyForm({
  company,
  onSubmit,
  onCancel,
  isLoading,
}: CompanyFormProps) {
  const isEditing = !!company;
  const { data: usersData } = useUsers();

  const ownerOptions = useMemo(
    () => [
      { value: '', label: '— Unassigned —' },
      ...((usersData ?? []) as Array<{ id: number; full_name: string }>).map((u) => ({
        value: String(u.id),
        label: u.full_name,
      })),
    ],
    [usersData]
  );

  const {
    register,
    handleSubmit,
    control,
    reset,
    setValue,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    defaultValues: {
      name: company?.name || '',
      website: company?.website || '',
      industry: company?.industry || '',
      company_size: company?.company_size || '',
      phone: company?.phone || '',
      email: company?.email || '',
      address_line1: company?.address_line1 || '',
      address_line2: company?.address_line2 || '',
      city: company?.city || '',
      state: company?.state || '',
      postal_code: company?.postal_code || '',
      country: company?.country || '',
      annual_revenue: company?.annual_revenue?.toLocaleString() || '',
      employee_count: company?.employee_count?.toLocaleString() || '',
      linkedin_url: company?.linkedin_url || '',
      twitter_handle: company?.twitter_handle || '',
      description: company?.description || '',
      link_creative_tier: company?.link_creative_tier || '',
      sow_url: company?.sow_url || '',
      account_manager: company?.account_manager || '',
      status: company?.status || 'prospect',
      segment: company?.segment || '',
      owner_id: company?.owner_id != null ? String(company.owner_id) : '',
    },
  });

  useUnsavedChangesWarning(isDirty);

  // Reset form when company prop changes
  useEffect(() => {
    if (company) {
      reset({
        name: company.name,
        website: company.website || '',
        industry: company.industry || '',
        company_size: company.company_size || '',
        phone: company.phone || '',
        email: company.email || '',
        address_line1: company.address_line1 || '',
        address_line2: company.address_line2 || '',
        city: company.city || '',
        state: company.state || '',
        postal_code: company.postal_code || '',
        country: company.country || '',
        annual_revenue: company.annual_revenue?.toLocaleString() || '',
        employee_count: company.employee_count?.toLocaleString() || '',
        linkedin_url: company.linkedin_url || '',
        twitter_handle: company.twitter_handle || '',
        description: company.description || '',
        link_creative_tier: company.link_creative_tier || '',
        sow_url: company.sow_url || '',
        account_manager: company.account_manager || '',
        status: company.status,
        segment: company.segment || '',
        owner_id: company.owner_id != null ? String(company.owner_id) : '',
      });
    }
  }, [company, reset]);

  const onFormSubmit = async (data: FormValues) => {
    // On update, cleared optional fields go out as null (not undefined)
    // so Pydantic sees them as `set` and the service applies the clear
    // — same pattern as the leads modal fix, since `exclude_unset=True`
    // would otherwise silently keep the old value. Required fields
    // (name, status) stay non-null.
    const clear = isEditing
      ? <T,>(v: T | undefined | null | ''): T | null => (v === '' || v == null ? null : v as T)
      : <T,>(v: T | undefined | null | ''): T | undefined => (v === '' || v == null ? undefined : v as T);

    const trimmed = (v: string) => v.trim();

    const formattedData = {
      name: data.name.trim(),
      website: clear(trimmed(data.website)),
      industry: clear(trimmed(data.industry)),
      company_size: clear(trimmed(data.company_size)),
      phone: clear(trimmed(data.phone)),
      email: clear(trimmed(data.email)),
      address_line1: clear(trimmed(data.address_line1)),
      address_line2: clear(trimmed(data.address_line2)),
      city: clear(trimmed(data.city)),
      state: clear(trimmed(data.state)),
      postal_code: clear(trimmed(data.postal_code)),
      country: clear(trimmed(data.country)),
      annual_revenue: parseLooseInt(data.annual_revenue) ?? (isEditing ? null : undefined),
      employee_count: parseLooseInt(data.employee_count) ?? (isEditing ? null : undefined),
      linkedin_url: clear(trimmed(data.linkedin_url)),
      twitter_handle: clear(trimmed(data.twitter_handle)),
      description: clear(trimmed(data.description)),
      link_creative_tier: clear(trimmed(data.link_creative_tier)),
      sow_url: clear(trimmed(data.sow_url)),
      account_manager: clear(trimmed(data.account_manager)),
      status: data.status,
      segment: clear(trimmed(data.segment)),
      owner_id: data.owner_id === '' ? (isEditing ? null : undefined) : Number(data.owner_id),
    };

    await onSubmit(formattedData);
  };

  const formRef = useFormSubmitShortcut();

  return (
    <form ref={formRef} onSubmit={handleSubmit(onFormSubmit)} className="space-y-4">
      {/* Basic Info */}
      <div className="grid grid-cols-2 gap-4">
        <Input
          {...register('name', { required: 'Company name is required' })}
          label="Company Name"
          autoComplete="organization"
          placeholder="Enter company name..."
          error={errors.name?.message}
        />
        <Controller
          name="status"
          control={control}
          render={({ field }) => (
            <Select {...field} label="Status" options={statusOptions} />
          )}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Input
          {...register('website')}
          type="url"
          label="Website"
          autoComplete="url"
          placeholder="https://example.com..."
        />
        <Input
          {...register('email')}
          type="email"
          label="Email"
          autoComplete="email"
          inputMode="email"
          spellCheck={false}
          placeholder="contact@example.com..."
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
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Controller
          name="industry"
          control={control}
          render={({ field }) => (
            <Select {...field} label="Industry" options={industryOptions} />
          )}
        />
        <Controller
          name="company_size"
          control={control}
          render={({ field }) => (
            <Select {...field} label="Company Size" options={companySizeOptions} />
          )}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Controller
          name="segment"
          control={control}
          render={({ field }) => (
            <Select {...field} label="Segment" options={segmentOptions} />
          )}
        />
        <Input
          {...register('phone')}
          type="tel"
          label="Phone"
          autoComplete="tel"
          inputMode="tel"
          placeholder="+1 (555) 000-0000..."
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

      {/* Business Info */}
      <div className="border-t pt-4 mt-4">
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Business Details</h4>
        <div className="grid grid-cols-2 gap-4">
          <Input
            {...register('annual_revenue')}
            type="number"
            label="Annual Revenue"
            placeholder="0"
          />
          <Input
            {...register('employee_count')}
            type="number"
            label="Employee Count"
            placeholder="0"
          />
        </div>
      </div>

      {/* Address */}
      <div className="border-t pt-4 mt-4">
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Address</h4>
        <Input
          {...register('address_line1')}
          label="Address Line 1"
          autoComplete="address-line1"
          placeholder="Street address..."
        />
        <div className="mt-4">
          <Input
            {...register('address_line2')}
            label="Address Line 2"
            autoComplete="address-line2"
            placeholder="Suite, unit, etc. (optional)"
          />
        </div>
        <div className="grid grid-cols-2 gap-4 mt-4">
          <Input
            {...register('city')}
            label="City"
            autoComplete="address-level2"
            placeholder="City..."
          />
          <Input
            {...register('state')}
            label="State/Province"
            autoComplete="address-level1"
            placeholder="State..."
          />
        </div>
        <div className="grid grid-cols-2 gap-4 mt-4">
          <Input
            {...register('postal_code')}
            label="Postal Code"
            autoComplete="postal-code"
            placeholder="Postal code..."
          />
          <Input
            {...register('country')}
            label="Country"
            autoComplete="country-name"
            placeholder="Country..."
          />
        </div>
      </div>

      {/* Social */}
      <div className="border-t pt-4 mt-4">
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Social Links</h4>
        <div className="grid grid-cols-2 gap-4">
          <Input
            {...register('linkedin_url')}
            type="url"
            label="LinkedIn URL"
            autoComplete="url"
            spellCheck={false}
            placeholder="https://linkedin.com/company/..."
          />
          <Input
            {...register('twitter_handle')}
            label="Twitter Handle"
            spellCheck={false}
            placeholder="@companyhandle..."
          />
        </div>
      </div>

      {/* Account & Creative */}
      <div className="border-t pt-4 mt-4">
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Account & Creative</h4>
        <div className="grid grid-cols-2 gap-4">
          <Controller
            name="owner_id"
            control={control}
            render={({ field }) => (
              <Select {...field} label="Owner" options={ownerOptions} />
            )}
          />
          <Controller
            name="link_creative_tier"
            control={control}
            render={({ field }) => (
              <Select {...field} label="Link Creative Tier" options={linkCreativeTierOptions} />
            )}
          />
          <Input
            {...register('account_manager')}
            label="Account Manager"
            placeholder="e.g. Jane Smith..."
          />
          <Input
            {...register('sow_url')}
            type="url"
            label="SOW URL"
            placeholder="https://..."
          />
        </div>
      </div>

      {/* Description */}
      <FormTextarea
        label="Description"
        name="description"
        rows={3}
        placeholder="Add notes about the company..."
        register={register('description')}
      />

      <div className="flex justify-end gap-3 pt-4 border-t">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" isLoading={isLoading}>
          {isEditing ? 'Update Company' : 'Create Company'}
        </Button>
      </div>
    </form>
  );
}

export default CompanyForm;

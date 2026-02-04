/**
 * Company form for creating/editing companies
 */

import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { Select } from '../../../components/ui/Select';
import type { Company, CompanyCreate, CompanyUpdate } from '../../../types';

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
  status: string;
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

export function CompanyForm({
  company,
  onSubmit,
  onCancel,
  isLoading,
}: CompanyFormProps) {
  const isEditing = !!company;

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
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
      annual_revenue: company?.annual_revenue?.toString() || '',
      employee_count: company?.employee_count?.toString() || '',
      linkedin_url: company?.linkedin_url || '',
      twitter_handle: company?.twitter_handle || '',
      description: company?.description || '',
      status: company?.status || 'prospect',
    },
  });

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
        annual_revenue: company.annual_revenue?.toString() || '',
        employee_count: company.employee_count?.toString() || '',
        linkedin_url: company.linkedin_url || '',
        twitter_handle: company.twitter_handle || '',
        description: company.description || '',
        status: company.status,
      });
    }
  }, [company, reset]);

  const onFormSubmit = async (data: FormValues) => {
    const formattedData = {
      name: data.name,
      website: data.website || undefined,
      industry: data.industry || undefined,
      company_size: data.company_size || undefined,
      phone: data.phone || undefined,
      email: data.email || undefined,
      address_line1: data.address_line1 || undefined,
      address_line2: data.address_line2 || undefined,
      city: data.city || undefined,
      state: data.state || undefined,
      postal_code: data.postal_code || undefined,
      country: data.country || undefined,
      annual_revenue: data.annual_revenue ? parseInt(data.annual_revenue, 10) : undefined,
      employee_count: data.employee_count ? parseInt(data.employee_count, 10) : undefined,
      linkedin_url: data.linkedin_url || undefined,
      twitter_handle: data.twitter_handle || undefined,
      description: data.description || undefined,
      status: data.status,
    };

    await onSubmit(formattedData);
  };

  return (
    <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-4">
      {/* Basic Info */}
      <div className="grid grid-cols-2 gap-4">
        <Input
          {...register('name', { required: 'Company name is required' })}
          label="Company Name"
          placeholder="Enter company name"
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
          label="Website"
          placeholder="https://example.com"
        />
        <Input
          {...register('email')}
          type="email"
          label="Email"
          placeholder="contact@example.com"
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

      <Input
        {...register('phone')}
        label="Phone"
        placeholder="+1 (555) 000-0000"
      />

      {/* Business Info */}
      <div className="border-t pt-4 mt-4">
        <h4 className="text-sm font-medium text-gray-700 mb-3">Business Details</h4>
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
        <h4 className="text-sm font-medium text-gray-700 mb-3">Address</h4>
        <Input
          {...register('address_line1')}
          label="Address Line 1"
          placeholder="Street address"
        />
        <div className="mt-4">
          <Input
            {...register('address_line2')}
            label="Address Line 2"
            placeholder="Suite, unit, etc. (optional)"
          />
        </div>
        <div className="grid grid-cols-2 gap-4 mt-4">
          <Input
            {...register('city')}
            label="City"
            placeholder="City"
          />
          <Input
            {...register('state')}
            label="State/Province"
            placeholder="State"
          />
        </div>
        <div className="grid grid-cols-2 gap-4 mt-4">
          <Input
            {...register('postal_code')}
            label="Postal Code"
            placeholder="Postal code"
          />
          <Input
            {...register('country')}
            label="Country"
            placeholder="Country"
          />
        </div>
      </div>

      {/* Social */}
      <div className="border-t pt-4 mt-4">
        <h4 className="text-sm font-medium text-gray-700 mb-3">Social Links</h4>
        <div className="grid grid-cols-2 gap-4">
          <Input
            {...register('linkedin_url')}
            label="LinkedIn URL"
            placeholder="https://linkedin.com/company/..."
          />
          <Input
            {...register('twitter_handle')}
            label="Twitter Handle"
            placeholder="@companyhandle"
          />
        </div>
      </div>

      {/* Description */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
        <textarea
          {...register('description')}
          rows={3}
          className="block w-full rounded-lg border border-gray-300 shadow-sm py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          placeholder="Add notes about the company"
        />
      </div>

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

/**
 * Campaign form for creating/editing campaigns
 */

import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { InformationCircleIcon } from '@heroicons/react/24/outline';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { Select } from '../../../components/ui/Select';
import { FormTextarea } from '../../../components/forms';
import { useUnsavedChangesWarning } from '../../../hooks/useUnsavedChangesWarning';
import type { Campaign, CampaignCreate, CampaignUpdate } from '../../../types';

interface CampaignFormProps {
  campaign?: Campaign;
  onSubmit: (data: CampaignCreate | CampaignUpdate) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
}

interface FormValues {
  name: string;
  description: string;
  campaign_type: string;
  status: string;
  start_date: string;
  end_date: string;
  budget_amount: string;
  budget_currency: string;
  target_audience: string;
  expected_revenue: string;
  expected_response: string;
}

const campaignTypeOptions = [
  { value: 'email', label: 'Email Campaign' },
  { value: 'event', label: 'Event' },
  { value: 'webinar', label: 'Webinar' },
  { value: 'ads', label: 'Advertising' },
  { value: 'social', label: 'Social Media' },
  { value: 'other', label: 'Other' },
];

const statusOptions = [
  { value: 'planned', label: 'Planned' },
  { value: 'active', label: 'Active' },
  { value: 'paused', label: 'Paused' },
  { value: 'completed', label: 'Completed' },
];

const currencyOptions = [
  { value: 'USD', label: 'USD ($)' },
  { value: 'EUR', label: 'EUR' },
  { value: 'GBP', label: 'GBP' },
  { value: 'INR', label: 'INR' },
];

function FieldHint({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 flex items-start gap-1">
      <InformationCircleIcon className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" aria-hidden="true" />
      <span>{children}</span>
    </p>
  );
}

function formatDateLocal(date: string | null | undefined): string {
  if (!date) return '';
  try {
    const d = new Date(date);
    return d.toISOString().slice(0, 10);
  } catch {
    return '';
  }
}

export function CampaignForm({
  campaign,
  onSubmit,
  onCancel,
  isLoading,
}: CampaignFormProps) {
  const isEditing = !!campaign;

  const {
    register,
    handleSubmit,
    control,
    reset,
    watch,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    defaultValues: {
      name: campaign?.name || '',
      description: campaign?.description || '',
      campaign_type: campaign?.campaign_type || 'email',
      status: campaign?.status || 'planned',
      start_date: formatDateLocal(campaign?.start_date),
      end_date: formatDateLocal(campaign?.end_date),
      budget_amount: campaign?.budget_amount?.toString() || '',
      budget_currency: campaign?.budget_currency || 'USD',
      target_audience: campaign?.target_audience || '',
      expected_revenue: campaign?.expected_revenue?.toString() || '',
      expected_response: campaign?.expected_response?.toString() || '',
    },
  });

  useUnsavedChangesWarning(isDirty);

  const selectedType = watch('campaign_type');

  // Reset form when campaign prop changes
  useEffect(() => {
    if (campaign) {
      reset({
        name: campaign.name,
        description: campaign.description || '',
        campaign_type: campaign.campaign_type,
        status: campaign.status,
        start_date: formatDateLocal(campaign.start_date),
        end_date: formatDateLocal(campaign.end_date),
        budget_amount: campaign.budget_amount?.toString() || '',
        budget_currency: campaign.budget_currency,
        target_audience: campaign.target_audience || '',
        expected_revenue: campaign.expected_revenue?.toString() || '',
        expected_response: campaign.expected_response?.toString() || '',
      });
    }
  }, [campaign, reset]);

  const onFormSubmit = async (data: FormValues) => {
    const formattedData = {
      name: data.name,
      description: data.description || undefined,
      campaign_type: data.campaign_type,
      status: data.status,
      start_date: data.start_date || undefined,
      end_date: data.end_date || undefined,
      budget_amount: data.budget_amount ? parseFloat(data.budget_amount) : undefined,
      budget_currency: data.budget_currency,
      target_audience: data.target_audience || undefined,
      expected_revenue: data.expected_revenue ? parseFloat(data.expected_revenue) : undefined,
      expected_response: data.expected_response ? parseInt(data.expected_response, 10) : undefined,
    };

    await onSubmit(formattedData);
  };

  return (
    <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-4">
      <Input
        {...register('name', { required: 'Campaign name is required' })}
        label="Campaign Name"
        placeholder="Enter campaign name"
        error={errors.name?.message}
      />

      <FormTextarea
        label="Description"
        name="description"
        rows={3}
        placeholder="Describe the campaign objectives and strategy"
        register={register('description')}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <Controller
            name="campaign_type"
            control={control}
            rules={{ required: 'Campaign type is required' }}
            render={({ field }) => (
              <Select
                {...field}
                label="Campaign Type"
                options={campaignTypeOptions}
                error={errors.campaign_type?.message}
              />
            )}
          />
        </div>

        <Controller
          name="status"
          control={control}
          render={({ field }) => (
            <Select {...field} label="Status" options={statusOptions} />
          )}
        />
      </div>

      {selectedType === 'email' && (
        <div className="rounded-md bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 p-3 text-sm text-blue-800 dark:text-blue-200">
          <p className="font-medium mb-0.5">After creating this campaign:</p>
          <p>Scroll to <strong>Campaign Sequence</strong> on the detail page to attach an email template and set the send schedule. Then click <strong>Add Members</strong> to load your recipient list.</p>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Input
          {...register('start_date')}
          type="date"
          label="Start Date"
          error={errors.start_date?.message}
        />
        <Input
          {...register('end_date')}
          type="date"
          label="End Date"
          error={errors.end_date?.message}
        />
      </div>

      <div className="border-t pt-4 mt-4">
        <h4 className="text-sm font-medium text-gray-700 mb-3">Budget & Goals</h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            {...register('budget_amount')}
            type="number"
            step="0.01"
            label="Budget Amount"
            placeholder="0.00"
          />
          <Controller
            name="budget_currency"
            control={control}
            render={({ field }) => (
              <Select {...field} label="Currency" options={currencyOptions} />
            )}
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
          <div>
            <Input
              {...register('expected_revenue')}
              type="number"
              step="0.01"
              label="Expected Revenue"
              placeholder="0.00"
            />
            <FieldHint>
              If this campaign converts at your historical rate, what dollar value do you expect to close?
            </FieldHint>
          </div>
          <div>
            <Input
              {...register('expected_response')}
              type="number"
              label="Expected Responses (target audience size)"
              placeholder="0"
            />
            <FieldHint>
              How many people are on the target list. This is a goal, not a hard cap.
            </FieldHint>
          </div>
        </div>
      </div>

      <div>
        <FormTextarea
          label="Target Audience"
          name="target_audience"
          rows={2}
          placeholder="e.g. CFOs at Chicago manufacturing companies, 50-250 employees..."
          register={register('target_audience')}
        />
        <FieldHint>
          One-line description of who you're sending this to (e.g. "CFOs at Chicago manufacturing companies, 50-250 employees").
        </FieldHint>
      </div>

      <div className="flex flex-col-reverse sm:flex-row justify-end gap-3 pt-4 border-t">
        <Button type="button" variant="secondary" onClick={onCancel} className="w-full sm:w-auto">
          Cancel
        </Button>
        <Button type="submit" isLoading={isLoading} className="w-full sm:w-auto">
          {isEditing ? 'Update Campaign' : 'Create Campaign'}
        </Button>
      </div>
    </form>
  );
}

export default CampaignForm;

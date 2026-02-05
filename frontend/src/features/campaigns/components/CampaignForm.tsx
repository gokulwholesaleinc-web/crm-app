/**
 * Campaign form for creating/editing campaigns
 */

import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { Select } from '../../../components/ui/Select';
import { FormTextarea } from '../../../components/forms';
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
    formState: { errors },
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

        <Controller
          name="status"
          control={control}
          render={({ field }) => (
            <Select {...field} label="Status" options={statusOptions} />
          )}
        />
      </div>

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
          <Input
            {...register('expected_revenue')}
            type="number"
            step="0.01"
            label="Expected Revenue"
            placeholder="0.00"
          />
          <Input
            {...register('expected_response')}
            type="number"
            label="Expected Responses"
            placeholder="0"
          />
        </div>
      </div>

      <FormTextarea
        label="Target Audience"
        name="target_audience"
        rows={2}
        placeholder="Describe the target audience for this campaign"
        register={register('target_audience')}
      />

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

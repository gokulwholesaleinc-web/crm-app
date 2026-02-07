/**
 * Workflow rule builder - form with dropdowns for trigger entity, event, conditions, actions
 */

import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { Select } from '../../../components/ui/Select';
import { FormTextarea } from '../../../components/forms';
import type { WorkflowRule, WorkflowRuleCreate, WorkflowRuleUpdate } from '../../../types';

interface WorkflowRuleBuilderProps {
  rule?: WorkflowRule;
  onSubmit: (data: WorkflowRuleCreate | WorkflowRuleUpdate) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
}

interface FormValues {
  name: string;
  description: string;
  is_active: boolean;
  trigger_entity: string;
  trigger_event: string;
  condition_field: string;
  condition_operator: string;
  condition_value: string;
  action_type: string;
  action_value: string;
}

const entityOptions = [
  { value: 'lead', label: 'Lead' },
  { value: 'contact', label: 'Contact' },
  { value: 'opportunity', label: 'Opportunity' },
  { value: 'activity', label: 'Activity' },
];

const eventOptions = [
  { value: 'created', label: 'Created' },
  { value: 'updated', label: 'Updated' },
  { value: 'status_changed', label: 'Status Changed' },
  { value: 'score_changed', label: 'Score Changed' },
];

const operatorOptions = [
  { value: '==', label: 'Equals (==)' },
  { value: '!=', label: 'Not Equals (!=)' },
  { value: '>=', label: 'Greater or Equal (>=)' },
  { value: '<=', label: 'Less or Equal (<=)' },
  { value: '>', label: 'Greater Than (>)' },
  { value: '<', label: 'Less Than (<)' },
  { value: 'contains', label: 'Contains' },
];

const actionTypeOptions = [
  { value: 'assign_owner', label: 'Assign Owner' },
  { value: 'create_activity', label: 'Create Activity' },
  { value: 'send_notification', label: 'Send Notification' },
  { value: 'update_field', label: 'Update Field' },
];

export function WorkflowRuleBuilder({
  rule,
  onSubmit,
  onCancel,
  isLoading,
}: WorkflowRuleBuilderProps) {
  const isEditing = !!rule;

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    defaultValues: {
      name: rule?.name || '',
      description: rule?.description || '',
      is_active: rule?.is_active ?? true,
      trigger_entity: rule?.trigger_entity || 'lead',
      trigger_event: rule?.trigger_event || 'created',
      condition_field: (rule?.conditions as Record<string, unknown>)?.field as string || '',
      condition_operator: (rule?.conditions as Record<string, unknown>)?.operator as string || '==',
      condition_value: String((rule?.conditions as Record<string, unknown>)?.value ?? ''),
      action_type: (rule?.actions?.[0] as Record<string, unknown>)?.type as string || '',
      action_value: String((rule?.actions?.[0] as Record<string, unknown>)?.value ?? ''),
    },
  });

  useEffect(() => {
    if (rule) {
      const conditions = rule.conditions as Record<string, unknown> | null;
      const firstAction = (rule.actions as Record<string, unknown>[] | null)?.[0] as Record<string, unknown> | undefined;
      reset({
        name: rule.name,
        description: rule.description || '',
        is_active: rule.is_active,
        trigger_entity: rule.trigger_entity,
        trigger_event: rule.trigger_event,
        condition_field: (conditions?.field as string) || '',
        condition_operator: (conditions?.operator as string) || '==',
        condition_value: String(conditions?.value ?? ''),
        action_type: (firstAction?.type as string) || '',
        action_value: String(firstAction?.value ?? ''),
      });
    }
  }, [rule, reset]);

  const onFormSubmit = async (data: FormValues) => {
    const conditions = data.condition_field
      ? {
          field: data.condition_field,
          operator: data.condition_operator,
          value: isNaN(Number(data.condition_value))
            ? data.condition_value
            : Number(data.condition_value),
        }
      : null;

    const actions = data.action_type
      ? [
          {
            type: data.action_type,
            value: isNaN(Number(data.action_value))
              ? data.action_value
              : Number(data.action_value),
          },
        ]
      : null;

    await onSubmit({
      name: data.name,
      description: data.description || undefined,
      is_active: data.is_active,
      trigger_entity: data.trigger_entity,
      trigger_event: data.trigger_event,
      conditions,
      actions,
    });
  };

  return (
    <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-4">
      <Input
        {...register('name', { required: 'Rule name is required' })}
        label="Rule Name"
        placeholder="e.g., High Score Lead Alert"
        error={errors.name?.message}
      />

      <FormTextarea
        label="Description"
        name="description"
        rows={2}
        placeholder="Describe what this rule does"
        register={register('description')}
      />

      <div className="flex items-center gap-3">
        <input
          type="checkbox"
          {...register('is_active')}
          className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
        />
        <label className="text-sm text-gray-700">Active</label>
      </div>

      {/* Trigger Configuration */}
      <div className="border-t pt-4">
        <h4 className="text-sm font-medium text-gray-700 mb-3">Trigger</h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Controller
            name="trigger_entity"
            control={control}
            rules={{ required: 'Entity is required' }}
            render={({ field }) => (
              <Select
                {...field}
                label="When this entity..."
                options={entityOptions}
                error={errors.trigger_entity?.message}
              />
            )}
          />
          <Controller
            name="trigger_event"
            control={control}
            rules={{ required: 'Event is required' }}
            render={({ field }) => (
              <Select
                {...field}
                label="...has this event"
                options={eventOptions}
                error={errors.trigger_event?.message}
              />
            )}
          />
        </div>
      </div>

      {/* Conditions */}
      <div className="border-t pt-4">
        <h4 className="text-sm font-medium text-gray-700 mb-3">Condition (optional)</h4>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Input
            {...register('condition_field')}
            label="Field"
            placeholder="e.g., score, status"
          />
          <Controller
            name="condition_operator"
            control={control}
            render={({ field }) => (
              <Select {...field} label="Operator" options={operatorOptions} />
            )}
          />
          <Input
            {...register('condition_value')}
            label="Value"
            placeholder="e.g., 80, qualified"
          />
        </div>
      </div>

      {/* Actions */}
      <div className="border-t pt-4">
        <h4 className="text-sm font-medium text-gray-700 mb-3">Action</h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Controller
            name="action_type"
            control={control}
            render={({ field }) => (
              <Select {...field} label="Action Type" options={[{ value: '', label: 'Select...' }, ...actionTypeOptions]} />
            )}
          />
          <Input
            {...register('action_value')}
            label="Action Value"
            placeholder="e.g., user ID, message"
          />
        </div>
      </div>

      <div className="flex flex-col-reverse sm:flex-row justify-end gap-3 pt-4 border-t">
        <Button type="button" variant="secondary" onClick={onCancel} className="w-full sm:w-auto">
          Cancel
        </Button>
        <Button type="submit" isLoading={isLoading} className="w-full sm:w-auto">
          {isEditing ? 'Update Rule' : 'Create Rule'}
        </Button>
      </div>
    </form>
  );
}

export default WorkflowRuleBuilder;

/**
 * Workflow rule form for creating/editing workflow rules
 */

import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { Select } from '../../../components/ui/Select';
import { FormTextarea } from '../../../components/forms';
import type { WorkflowRule, WorkflowRuleCreate, WorkflowRuleUpdate } from '../../../types';

interface WorkflowFormProps {
  workflow?: WorkflowRule;
  onSubmit: (data: WorkflowRuleCreate | WorkflowRuleUpdate) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
}

interface FormValues {
  name: string;
  description: string;
  trigger_entity: string;
  trigger_event: string;
  is_active: boolean;
  conditions: string;
  actions: string;
}

const triggerEntityOptions = [
  { value: 'lead', label: 'Lead' },
  { value: 'contact', label: 'Contact' },
  { value: 'company', label: 'Company' },
  { value: 'opportunity', label: 'Opportunity' },
  { value: 'activity', label: 'Activity' },
];

const triggerEventOptions = [
  { value: 'created', label: 'Created' },
  { value: 'updated', label: 'Updated' },
  { value: 'deleted', label: 'Deleted' },
  { value: 'status_changed', label: 'Status Changed' },
  { value: 'assigned', label: 'Assigned' },
];

function safeJsonStringify(value: unknown): string {
  if (!value) return '';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return '';
  }
}

function safeJsonParse(value: string): unknown | undefined {
  if (!value.trim()) return undefined;
  try {
    return JSON.parse(value);
  } catch {
    return undefined;
  }
}

export function WorkflowForm({
  workflow,
  onSubmit,
  onCancel,
  isLoading,
}: WorkflowFormProps) {
  const isEditing = !!workflow;

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    defaultValues: {
      name: workflow?.name || '',
      description: workflow?.description || '',
      trigger_entity: workflow?.trigger_entity || 'lead',
      trigger_event: workflow?.trigger_event || 'created',
      is_active: workflow?.is_active ?? true,
      conditions: safeJsonStringify(workflow?.conditions),
      actions: safeJsonStringify(workflow?.actions),
    },
  });

  useEffect(() => {
    if (workflow) {
      reset({
        name: workflow.name,
        description: workflow.description || '',
        trigger_entity: workflow.trigger_entity,
        trigger_event: workflow.trigger_event,
        is_active: workflow.is_active,
        conditions: safeJsonStringify(workflow.conditions),
        actions: safeJsonStringify(workflow.actions),
      });
    }
  }, [workflow, reset]);

  const onFormSubmit = async (data: FormValues) => {
    const formattedData: WorkflowRuleCreate | WorkflowRuleUpdate = {
      name: data.name,
      description: data.description || undefined,
      trigger_entity: data.trigger_entity,
      trigger_event: data.trigger_event,
      is_active: data.is_active,
      conditions: safeJsonParse(data.conditions) as Record<string, unknown> | undefined,
      actions: safeJsonParse(data.actions) as Record<string, unknown>[] | undefined,
    };

    await onSubmit(formattedData);
  };

  const validateJson = (value: string) => {
    if (!value.trim()) return true;
    try {
      JSON.parse(value);
      return true;
    } catch {
      return 'Invalid JSON format';
    }
  };

  return (
    <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-4">
      <Input
        {...register('name', { required: 'Workflow name is required' })}
        label="Workflow Name"
        placeholder="Enter workflow name"
        error={errors.name?.message}
      />

      <FormTextarea
        label="Description"
        name="description"
        rows={2}
        placeholder="Describe what this workflow does"
        register={register('description')}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Controller
          name="trigger_entity"
          control={control}
          rules={{ required: 'Trigger entity is required' }}
          render={({ field }) => (
            <Select
              {...field}
              label="Trigger Entity"
              options={triggerEntityOptions}
              error={errors.trigger_entity?.message}
            />
          )}
        />

        <Controller
          name="trigger_event"
          control={control}
          rules={{ required: 'Trigger event is required' }}
          render={({ field }) => (
            <Select
              {...field}
              label="Trigger Event"
              options={triggerEventOptions}
              error={errors.trigger_event?.message}
            />
          )}
        />
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="is_active"
          {...register('is_active')}
          className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
        />
        <label htmlFor="is_active" className="text-sm font-medium text-gray-700">
          Active
        </label>
      </div>

      <FormTextarea
        label="Conditions (JSON)"
        name="conditions"
        rows={3}
        placeholder='{"field": "status", "operator": "equals", "value": "qualified"}'
        register={register('conditions', { validate: validateJson })}
        error={errors.conditions?.message}
        helperText="Optional JSON object defining when this workflow triggers"
      />

      <FormTextarea
        label="Actions (JSON)"
        name="actions"
        rows={3}
        placeholder='[{"type": "send_email", "template": "welcome"}]'
        register={register('actions', { validate: validateJson })}
        error={errors.actions?.message}
        helperText="Optional JSON array of actions to execute"
      />

      <div className="flex flex-col-reverse sm:flex-row justify-end gap-3 pt-4 border-t">
        <Button type="button" variant="secondary" onClick={onCancel} className="w-full sm:w-auto">
          Cancel
        </Button>
        <Button type="submit" isLoading={isLoading} className="w-full sm:w-auto">
          {isEditing ? 'Update Workflow' : 'Create Workflow'}
        </Button>
      </div>
    </form>
  );
}

export default WorkflowForm;

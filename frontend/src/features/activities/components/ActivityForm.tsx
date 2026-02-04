/**
 * Form for creating/editing activities (handles all types: call, email, meeting, task, note)
 */

import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { Select } from '../../../components/ui/Select';
import type { Activity, ActivityCreate, ActivityUpdate } from '../../../types';

interface ActivityFormProps {
  activity?: Activity;
  entityType: string;
  entityId: number;
  onSubmit: (data: ActivityCreate | ActivityUpdate) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
}

interface FormValues {
  activity_type: string;
  subject: string;
  description: string;
  scheduled_at: string;
  due_date: string;
  priority: string;
  // Call-specific
  call_duration_minutes: string;
  call_outcome: string;
  // Email-specific
  email_to: string;
  email_cc: string;
  // Meeting-specific
  meeting_location: string;
  meeting_attendees: string;
  // Task-specific
  task_reminder_at: string;
}

const activityTypeOptions = [
  { value: 'call', label: 'Call' },
  { value: 'email', label: 'Email' },
  { value: 'meeting', label: 'Meeting' },
  { value: 'task', label: 'Task' },
  { value: 'note', label: 'Note' },
];

const priorityOptions = [
  { value: 'low', label: 'Low' },
  { value: 'normal', label: 'Normal' },
  { value: 'high', label: 'High' },
  { value: 'urgent', label: 'Urgent' },
];

const callOutcomeOptions = [
  { value: '', label: 'Select outcome...' },
  { value: 'connected', label: 'Connected' },
  { value: 'voicemail', label: 'Left Voicemail' },
  { value: 'no_answer', label: 'No Answer' },
  { value: 'busy', label: 'Busy' },
];

function formatDateTimeLocal(date: string | null | undefined): string {
  if (!date) return '';
  try {
    const d = new Date(date);
    return d.toISOString().slice(0, 16);
  } catch {
    return '';
  }
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

export function ActivityForm({
  activity,
  entityType,
  entityId,
  onSubmit,
  onCancel,
  isLoading,
}: ActivityFormProps) {
  const isEditing = !!activity;

  const {
    register,
    handleSubmit,
    watch,
    control,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    defaultValues: {
      activity_type: activity?.activity_type || 'task',
      subject: activity?.subject || '',
      description: activity?.description || '',
      scheduled_at: formatDateTimeLocal(activity?.scheduled_at),
      due_date: formatDateLocal(activity?.due_date),
      priority: activity?.priority || 'normal',
      call_duration_minutes: activity?.call_duration_minutes?.toString() || '',
      call_outcome: activity?.call_outcome || '',
      email_to: activity?.email_to || '',
      email_cc: activity?.email_cc || '',
      meeting_location: activity?.meeting_location || '',
      meeting_attendees: activity?.meeting_attendees || '',
      task_reminder_at: formatDateTimeLocal(activity?.task_reminder_at),
    },
  });

  const activityType = watch('activity_type');

  // Reset form when activity prop changes
  useEffect(() => {
    if (activity) {
      reset({
        activity_type: activity.activity_type,
        subject: activity.subject,
        description: activity.description || '',
        scheduled_at: formatDateTimeLocal(activity.scheduled_at),
        due_date: formatDateLocal(activity.due_date),
        priority: activity.priority,
        call_duration_minutes: activity.call_duration_minutes?.toString() || '',
        call_outcome: activity.call_outcome || '',
        email_to: activity.email_to || '',
        email_cc: activity.email_cc || '',
        meeting_location: activity.meeting_location || '',
        meeting_attendees: activity.meeting_attendees || '',
        task_reminder_at: formatDateTimeLocal(activity.task_reminder_at),
      });
    }
  }, [activity, reset]);

  const onFormSubmit = async (data: FormValues) => {
    const baseData = {
      activity_type: data.activity_type,
      subject: data.subject,
      description: data.description || undefined,
      scheduled_at: data.scheduled_at ? new Date(data.scheduled_at).toISOString() : undefined,
      due_date: data.due_date || undefined,
      priority: data.priority,
    };

    // Add type-specific fields
    const typeSpecificFields: Partial<ActivityCreate> = {};

    if (data.activity_type === 'call') {
      if (data.call_duration_minutes) {
        typeSpecificFields.call_duration_minutes = parseInt(data.call_duration_minutes, 10);
      }
      if (data.call_outcome) {
        typeSpecificFields.call_outcome = data.call_outcome;
      }
    }

    if (data.activity_type === 'email') {
      if (data.email_to) typeSpecificFields.email_to = data.email_to;
      if (data.email_cc) typeSpecificFields.email_cc = data.email_cc;
    }

    if (data.activity_type === 'meeting') {
      if (data.meeting_location) typeSpecificFields.meeting_location = data.meeting_location;
      if (data.meeting_attendees) typeSpecificFields.meeting_attendees = data.meeting_attendees;
    }

    if (data.activity_type === 'task') {
      if (data.task_reminder_at) {
        typeSpecificFields.task_reminder_at = new Date(data.task_reminder_at).toISOString();
      }
    }

    if (isEditing) {
      await onSubmit({
        ...baseData,
        ...typeSpecificFields,
      } as ActivityUpdate);
    } else {
      await onSubmit({
        ...baseData,
        ...typeSpecificFields,
        entity_type: entityType,
        entity_id: entityId,
      } as ActivityCreate);
    }
  };

  return (
    <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <Controller
          name="activity_type"
          control={control}
          rules={{ required: 'Activity type is required' }}
          render={({ field }) => (
            <Select
              {...field}
              label="Activity Type"
              options={activityTypeOptions}
              error={errors.activity_type?.message}
              disabled={isEditing}
            />
          )}
        />

        <Controller
          name="priority"
          control={control}
          render={({ field }) => (
            <Select {...field} label="Priority" options={priorityOptions} />
          )}
        />
      </div>

      <Input
        {...register('subject', { required: 'Subject is required' })}
        label="Subject"
        placeholder="Enter activity subject"
        error={errors.subject?.message}
      />

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
        <textarea
          {...register('description')}
          rows={3}
          className="block w-full rounded-lg border border-gray-300 shadow-sm py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          placeholder="Enter activity description (optional)"
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Input
          {...register('scheduled_at')}
          type="datetime-local"
          label="Scheduled At"
          error={errors.scheduled_at?.message}
        />

        <Input
          {...register('due_date')}
          type="date"
          label="Due Date"
          error={errors.due_date?.message}
        />
      </div>

      {/* Call-specific fields */}
      {activityType === 'call' && (
        <div className="border-t pt-4 mt-4">
          <h4 className="text-sm font-medium text-gray-700 mb-3">Call Details</h4>
          <div className="grid grid-cols-2 gap-4">
            <Input
              {...register('call_duration_minutes')}
              type="number"
              label="Duration (minutes)"
              placeholder="Enter call duration"
            />
            <Controller
              name="call_outcome"
              control={control}
              render={({ field }) => (
                <Select {...field} label="Call Outcome" options={callOutcomeOptions} />
              )}
            />
          </div>
        </div>
      )}

      {/* Email-specific fields */}
      {activityType === 'email' && (
        <div className="border-t pt-4 mt-4">
          <h4 className="text-sm font-medium text-gray-700 mb-3">Email Details</h4>
          <div className="grid grid-cols-2 gap-4">
            <Input
              {...register('email_to')}
              type="email"
              label="To"
              placeholder="recipient@example.com"
            />
            <Input
              {...register('email_cc')}
              type="email"
              label="CC"
              placeholder="cc@example.com"
            />
          </div>
        </div>
      )}

      {/* Meeting-specific fields */}
      {activityType === 'meeting' && (
        <div className="border-t pt-4 mt-4">
          <h4 className="text-sm font-medium text-gray-700 mb-3">Meeting Details</h4>
          <Input
            {...register('meeting_location')}
            label="Location"
            placeholder="Enter meeting location or link"
          />
          <div className="mt-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">Attendees</label>
            <textarea
              {...register('meeting_attendees')}
              rows={2}
              className="block w-full rounded-lg border border-gray-300 shadow-sm py-2 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              placeholder="Enter attendee names or emails (one per line)"
            />
          </div>
        </div>
      )}

      {/* Task-specific fields */}
      {activityType === 'task' && (
        <div className="border-t pt-4 mt-4">
          <h4 className="text-sm font-medium text-gray-700 mb-3">Task Details</h4>
          <Input
            {...register('task_reminder_at')}
            type="datetime-local"
            label="Reminder At"
          />
        </div>
      )}

      <div className="flex justify-end gap-3 pt-4 border-t">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" isLoading={isLoading}>
          {isEditing ? 'Update Activity' : 'Create Activity'}
        </Button>
      </div>
    </form>
  );
}

export default ActivityForm;

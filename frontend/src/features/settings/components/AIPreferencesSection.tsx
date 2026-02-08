import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import {
  useAIPreferences,
  useUpdateAIPreferences,
} from '../../../hooks/useAI';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Spinner } from '../../../components/ui/Spinner';
import { Button } from '../../../components/ui/Button';
import { FormSelect, FormTextarea } from '../../../components/forms';
import { PencilSquareIcon } from '@heroicons/react/24/outline';

interface AIPreferencesFormData {
  preferred_communication_style: string;
  custom_instructions: string;
}

export function AIPreferencesSection() {
  const { data: preferences, isLoading } = useAIPreferences();
  const updateMutation = useUpdateAIPreferences();
  const [isEditing, setIsEditing] = useState(false);
  const [success, setSuccess] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
  } = useForm<AIPreferencesFormData>();

  useEffect(() => {
    if (isEditing && preferences) {
      reset({
        preferred_communication_style: preferences.preferred_communication_style || 'professional',
        custom_instructions: preferences.custom_instructions || '',
      });
    }
  }, [isEditing, preferences, reset]);

  const onSubmit = async (data: AIPreferencesFormData) => {
    try {
      await updateMutation.mutateAsync({
        preferred_communication_style: data.preferred_communication_style,
        custom_instructions: data.custom_instructions || null,
      });
      setSuccess(true);
      setTimeout(() => {
        setIsEditing(false);
        setSuccess(false);
      }, 1000);
    } catch {
      // error handled by mutation state
    }
  };

  const communicationStyles = [
    { value: 'professional', label: 'Professional' },
    { value: 'casual', label: 'Casual' },
    { value: 'concise', label: 'Concise' },
    { value: 'detailed', label: 'Detailed' },
  ];

  return (
    <Card>
      <CardHeader
        title="AI Preferences"
        description="Configure how the AI assistant communicates with you"
        action={
          !isEditing ? (
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<PencilSquareIcon className="h-4 w-4" />}
              onClick={() => setIsEditing(true)}
            >
              Edit
            </Button>
          ) : undefined
        }
      />
      <CardBody className="p-4 sm:p-6">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Spinner size="md" />
          </div>
        ) : isEditing ? (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            {success && (
              <div className="rounded-md bg-green-50 p-3">
                <p className="text-sm text-green-800">Preferences saved successfully!</p>
              </div>
            )}
            {updateMutation.isError && (
              <div className="rounded-md bg-red-50 p-3">
                <p className="text-sm text-red-800">Failed to save preferences. Please try again.</p>
              </div>
            )}

            <FormSelect
              label="Communication Style"
              name="preferred_communication_style"
              options={communicationStyles}
              register={register('preferred_communication_style')}
              helperText="How should the AI assistant communicate with you?"
            />

            <FormTextarea
              label="Custom Instructions"
              name="custom_instructions"
              rows={3}
              placeholder="e.g., Always prioritize high-value deals, focus on enterprise clients..."
              register={register('custom_instructions')}
              helperText="Additional instructions for the AI assistant"
            />

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => { setIsEditing(false); setSuccess(false); }}
                disabled={updateMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                isLoading={updateMutation.isPending}
                disabled={success}
              >
                Save Preferences
              </Button>
            </div>
          </form>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-3 sm:gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-xs sm:text-sm font-medium text-gray-500">
                  Communication Style
                </label>
                <p className="mt-1 text-sm text-gray-900 capitalize">
                  {preferences?.preferred_communication_style || 'Professional'}
                </p>
              </div>
              <div>
                <label className="block text-xs sm:text-sm font-medium text-gray-500">
                  Custom Instructions
                </label>
                <p className="mt-1 text-sm text-gray-900">
                  {preferences?.custom_instructions || 'None set'}
                </p>
              </div>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

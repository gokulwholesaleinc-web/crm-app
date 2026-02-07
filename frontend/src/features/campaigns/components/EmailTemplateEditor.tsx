/**
 * Email template editor - form for creating/editing email templates
 */

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { Button } from '../../../components/ui/Button';
import { Input } from '../../../components/ui/Input';
import { FormTextarea } from '../../../components/forms';
import type { EmailTemplate, EmailTemplateCreate, EmailTemplateUpdate } from '../../../types';

interface EmailTemplateEditorProps {
  template?: EmailTemplate;
  onSubmit: (data: EmailTemplateCreate | EmailTemplateUpdate) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
}

interface FormValues {
  name: string;
  subject_template: string;
  body_template: string;
  category: string;
}

export function EmailTemplateEditor({
  template,
  onSubmit,
  onCancel,
  isLoading,
}: EmailTemplateEditorProps) {
  const isEditing = !!template;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    defaultValues: {
      name: template?.name || '',
      subject_template: template?.subject_template || '',
      body_template: template?.body_template || '',
      category: template?.category || '',
    },
  });

  useEffect(() => {
    if (template) {
      reset({
        name: template.name,
        subject_template: template.subject_template,
        body_template: template.body_template,
        category: template.category || '',
      });
    }
  }, [template, reset]);

  const onFormSubmit = async (data: FormValues) => {
    const formattedData = {
      name: data.name,
      subject_template: data.subject_template,
      body_template: data.body_template,
      category: data.category || undefined,
    };
    await onSubmit(formattedData);
  };

  return (
    <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-4">
      <Input
        {...register('name', { required: 'Template name is required' })}
        label="Template Name"
        placeholder="e.g., Welcome Email, Follow Up"
        error={errors.name?.message}
      />

      <Input
        {...register('category')}
        label="Category"
        placeholder="e.g., onboarding, follow_up, newsletter"
      />

      <Input
        {...register('subject_template', { required: 'Subject is required' })}
        label="Subject Line"
        placeholder="e.g., Welcome to {{company_name}}!"
        error={errors.subject_template?.message}
      />

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Email Body
        </label>
        <p className="text-xs text-gray-500 mb-2">
          Use {'{{variable_name}}'} for merge fields (e.g., {'{{first_name}}'}, {'{{company_name}}'})
        </p>
        <FormTextarea
          label=""
          name="body_template"
          rows={8}
          placeholder="<h1>Hello {{first_name}}</h1>\n<p>Your email content here...</p>"
          register={register('body_template', { required: 'Body is required' })}
          error={errors.body_template?.message}
        />
      </div>

      <div className="flex flex-col-reverse sm:flex-row justify-end gap-3 pt-4 border-t">
        <Button type="button" variant="secondary" onClick={onCancel} className="w-full sm:w-auto">
          Cancel
        </Button>
        <Button type="submit" isLoading={isLoading} className="w-full sm:w-auto">
          {isEditing ? 'Update Template' : 'Create Template'}
        </Button>
      </div>
    </form>
  );
}

export default EmailTemplateEditor;

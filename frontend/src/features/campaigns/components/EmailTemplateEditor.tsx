/**
 * Email template editor - form for creating/editing email templates.
 * Includes branded preview mode.
 */

import { useEffect, useState } from 'react';
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
  const [showPreview, setShowPreview] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    defaultValues: {
      name: template?.name || '',
      subject_template: template?.subject_template || '',
      body_template: template?.body_template || '',
      category: template?.category || '',
    },
  });

  const bodyValue = watch('body_template');
  const subjectValue = watch('subject_template');

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
    <div className="space-y-4">
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
          <label htmlFor="body_template" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Email Body
          </label>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
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

        {/* Branded template notice */}
        <div className="rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-900/20 p-3">
          <p className="text-sm text-blue-700 dark:text-blue-300">
            Your email will be wrapped in your organization's branded template, including your
            logo, colors, and footer with an unsubscribe link.
          </p>
        </div>

        <div className="flex flex-col-reverse sm:flex-row justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
          <Button type="button" variant="secondary" onClick={onCancel} className="w-full sm:w-auto">
            Cancel
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setShowPreview((prev) => !prev)}
            className="w-full sm:w-auto"
            aria-label={showPreview ? 'Hide branded preview' : 'Show branded preview'}
          >
            {showPreview ? 'Hide Preview' : 'Preview Branded'}
          </Button>
          <Button type="submit" isLoading={isLoading} className="w-full sm:w-auto">
            {isEditing ? 'Update Template' : 'Create Template'}
          </Button>
        </div>
      </form>

      {/* Branded preview panel */}
      {showPreview && (
        <div className="mt-4 space-y-2">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
            Branded Preview
          </h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Approximate preview of your email in the branded wrapper. Actual appearance
            may vary by email client.
          </p>
          <div className="rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
            {/* Simulated branded header */}
            <div className="bg-indigo-500 px-6 py-4 text-white font-bold text-lg">
              Your Company
            </div>
            {/* Subject */}
            <div className="bg-white dark:bg-gray-800 px-6 pt-4 pb-2 border-b border-gray-100 dark:border-gray-700">
              <p className="text-xs text-gray-400 dark:text-gray-500">Subject:</p>
              <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {subjectValue || '(No subject)'}
              </p>
            </div>
            {/* Body content */}
            <div className="bg-white dark:bg-gray-800 px-6 py-6">
              <div
                className="prose prose-sm dark:prose-invert max-w-none text-gray-700 dark:text-gray-300"
                dangerouslySetInnerHTML={{ __html: bodyValue || '<p>(No body content)</p>' }}
              />
            </div>
            {/* Simulated branded footer */}
            <div className="bg-gray-50 dark:bg-gray-900 px-6 py-4 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400 font-semibold">Your Company</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                <span className="underline cursor-pointer">Unsubscribe</span>
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default EmailTemplateEditor;

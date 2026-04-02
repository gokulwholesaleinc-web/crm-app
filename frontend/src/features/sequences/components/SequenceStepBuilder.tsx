/**
 * Visual sequence step builder with flow layout, template picker, and reorder controls.
 * Replaces the inline StepBuilder in SequencesPage with a more polished UX.
 */

import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '../../../components/ui/Button';
import { listEmailTemplates } from '../../../api/campaigns';
import type { SequenceStep, EmailTemplate } from '../../../types';
import {
  TrashIcon,
  EnvelopeIcon,
  ClockIcon,
  ClipboardDocumentListIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';

const STEP_CONFIG: Record<string, { icon: React.ComponentType<{ className?: string }>; label: string; color: string; bg: string }> = {
  email: {
    icon: EnvelopeIcon,
    label: 'Send Email',
    color: 'text-blue-600 dark:text-blue-400',
    bg: 'bg-blue-100 dark:bg-blue-900/30 border-blue-200 dark:border-blue-800',
  },
  wait: {
    icon: ClockIcon,
    label: 'Wait',
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800',
  },
  task: {
    icon: ClipboardDocumentListIcon,
    label: 'Create Task',
    color: 'text-purple-600 dark:text-purple-400',
    bg: 'bg-purple-50 dark:bg-purple-900/20 border-purple-200 dark:border-purple-800',
  },
};

interface SequenceStepBuilderProps {
  steps: SequenceStep[];
  onChange: (steps: SequenceStep[]) => void;
}

export function SequenceStepBuilder({ steps, onChange }: SequenceStepBuilderProps) {
  const { data: templates = [] } = useQuery<EmailTemplate[]>({
    queryKey: ['email-templates'],
    queryFn: () => listEmailTemplates(),
  });

  const addStep = useCallback((type: 'email' | 'task' | 'wait') => {
    const newStep: SequenceStep = {
      step_number: steps.length,
      type,
      delay_days: type === 'wait' ? 1 : 0,
      ...(type === 'email' ? { template_id: templates[0]?.id } : {}),
      ...(type === 'task' ? { task_description: '' } : {}),
    };
    onChange([...steps, newStep]);
  }, [steps, onChange, templates]);

  const updateStep = useCallback((index: number, updates: Partial<SequenceStep>) => {
    onChange(steps.map((s, i) => (i === index ? { ...s, ...updates } : s)));
  }, [steps, onChange]);

  const removeStep = useCallback((index: number) => {
    onChange(steps.filter((_, i) => i !== index).map((s, i) => ({ ...s, step_number: i })));
  }, [steps, onChange]);

  const moveStep = useCallback((index: number, direction: -1 | 1) => {
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= steps.length) return;
    const reordered = [...steps];
    [reordered[index], reordered[newIndex]] = [reordered[newIndex], reordered[index]];
    onChange(reordered.map((s, i) => ({ ...s, step_number: i })));
  }, [steps, onChange]);

  const totalDays = steps.reduce((sum, s) => sum + (s.delay_days || 0), 0);

  return (
    <div className="space-y-1">
      {/* Flow header */}
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {steps.length} step{steps.length !== 1 ? 's' : ''} · {totalDays} day{totalDays !== 1 ? 's' : ''} total
        </p>
      </div>

      {/* Steps with connectors */}
      {steps.map((step, index) => {
        const config = STEP_CONFIG[step.type] || STEP_CONFIG.wait;
        const Icon = config.icon;
        const templateName = step.type === 'email' && step.template_id
          ? templates.find(t => t.id === step.template_id)?.name
          : null;

        return (
          <div key={index}>
            {/* Connector line */}
            {index > 0 && (
              <div className="flex items-center justify-center py-1">
                <div className="w-px h-4 bg-gray-300 dark:bg-gray-600" />
              </div>
            )}

            {/* Delay badge between steps */}
            {index > 0 && step.delay_days > 0 && (
              <div className="flex items-center justify-center -mt-1 -mb-1">
                <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 dark:bg-gray-700 px-2 py-0.5 text-xs text-gray-600 dark:text-gray-400">
                  <ClockIcon className="h-3 w-3" aria-hidden="true" />
                  {step.delay_days}d delay
                </span>
              </div>
            )}
            {index > 0 && (
              <div className="flex items-center justify-center py-1">
                <div className="w-px h-4 bg-gray-300 dark:bg-gray-600" />
              </div>
            )}

            {/* Step card */}
            <div className={`border rounded-lg p-3 ${config.bg}`}>
              <div className="flex items-start gap-3">
                {/* Step number + icon */}
                <div className={`flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center bg-white dark:bg-gray-800 shadow-sm ${config.color}`}>
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </div>

                {/* Step content */}
                <div className="flex-1 min-w-0 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className={`text-sm font-medium ${config.color}`}>
                      {config.label}
                    </span>
                    <span className="text-xs text-gray-400">#{index + 1}</span>
                  </div>

                  {/* Email template picker */}
                  {step.type === 'email' && (
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Email Template</label>
                      <select
                        value={step.template_id || ''}
                        onChange={(e) => updateStep(index, { template_id: e.target.value ? parseInt(e.target.value, 10) : undefined })}
                        className="w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 text-sm py-1.5"
                        aria-label="Select email template"
                      >
                        <option value="">Select template...</option>
                        {templates.map(t => (
                          <option key={t.id} value={t.id}>{t.name}</option>
                        ))}
                      </select>
                      {templateName && (
                        <p className="text-xs text-gray-500 mt-1">Subject: {templates.find(t => t.id === step.template_id)?.subject_template}</p>
                      )}
                    </div>
                  )}

                  {/* Wait days input */}
                  {step.type === 'wait' && (
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-gray-500 dark:text-gray-400">Wait for</label>
                      <input
                        type="number"
                        min="1"
                        value={step.delay_days}
                        onChange={(e) => updateStep(index, { delay_days: parseInt(e.target.value, 10) || 1 })}
                        className="w-16 rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 text-sm py-1"
                        aria-label="Wait days"
                      />
                      <span className="text-xs text-gray-500 dark:text-gray-400">day{(step.delay_days || 0) !== 1 ? 's' : ''}</span>
                    </div>
                  )}

                  {/* Task description */}
                  {step.type === 'task' && (
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Task Description</label>
                      <input
                        type="text"
                        value={step.task_description || ''}
                        onChange={(e) => updateStep(index, { task_description: e.target.value })}
                        placeholder="Describe the task..."
                        className="w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 text-sm py-1.5"
                        aria-label="Task description"
                      />
                    </div>
                  )}

                  {/* Delay for non-wait steps */}
                  {step.type !== 'wait' && (
                    <div className="flex items-center gap-2">
                      <label className="text-xs text-gray-500 dark:text-gray-400">Delay</label>
                      <input
                        type="number"
                        min="0"
                        value={step.delay_days}
                        onChange={(e) => updateStep(index, { delay_days: parseInt(e.target.value, 10) || 0 })}
                        className="w-16 rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 text-sm py-1"
                        aria-label="Step delay days"
                      />
                      <span className="text-xs text-gray-500 dark:text-gray-400">days after previous step</span>
                    </div>
                  )}
                </div>

                {/* Controls */}
                <div className="flex flex-col gap-1 flex-shrink-0">
                  <button
                    type="button"
                    onClick={() => moveStep(index, -1)}
                    disabled={index === 0}
                    className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-30"
                    aria-label="Move step up"
                  >
                    <ChevronUpIcon className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => moveStep(index, 1)}
                    disabled={index === steps.length - 1}
                    className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-30"
                    aria-label="Move step down"
                  >
                    <ChevronDownIcon className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => removeStep(index)}
                    className="p-1 text-gray-400 hover:text-red-500"
                    aria-label={`Remove step ${index + 1}`}
                  >
                    <TrashIcon className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        );
      })}

      {/* Empty state */}
      {steps.length === 0 && (
        <div className="text-center py-8 border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-lg">
          <PlusIcon className="mx-auto h-8 w-8 text-gray-400" aria-hidden="true" />
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">Add steps to build your sequence</p>
        </div>
      )}

      {/* Add step buttons */}
      <div className="flex items-center gap-2 pt-3 border-t border-gray-200 dark:border-gray-700 mt-3">
        <span className="text-xs text-gray-500 dark:text-gray-400 mr-1">Add:</span>
        <Button type="button" variant="secondary" size="sm" leftIcon={<EnvelopeIcon className="h-4 w-4" />} onClick={() => addStep('email')}>
          Email
        </Button>
        <Button type="button" variant="secondary" size="sm" leftIcon={<ClockIcon className="h-4 w-4" />} onClick={() => addStep('wait')}>
          Wait
        </Button>
        <Button type="button" variant="secondary" size="sm" leftIcon={<ClipboardDocumentListIcon className="h-4 w-4" />} onClick={() => addStep('task')}>
          Task
        </Button>
      </div>
    </div>
  );
}

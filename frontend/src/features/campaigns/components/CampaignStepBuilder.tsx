/**
 * Campaign step builder - list of ordered steps in an email sequence
 */

import { useState } from 'react';
import {
  ArrowUpIcon,
  ArrowDownIcon,
  TrashIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';
import { Button } from '../../../components/ui/Button';
import type { EmailCampaignStep, EmailTemplate } from '../../../types';

interface CampaignStepBuilderProps {
  steps: EmailCampaignStep[];
  templates: EmailTemplate[];
  onAddStep: (templateId: number, delayDays: number, stepOrder: number) => Promise<void>;
  onUpdateStep: (stepId: number, data: { delay_days?: number; step_order?: number }) => Promise<void>;
  onDeleteStep: (stepId: number) => Promise<void>;
  isLoading?: boolean;
}

export function CampaignStepBuilder({
  steps,
  templates,
  onAddStep,
  onUpdateStep,
  onDeleteStep,
  isLoading,
}: CampaignStepBuilderProps) {
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | ''>('');
  const [delayDays, setDelayDays] = useState<number>(0);

  const sortedSteps = [...steps].sort((a, b) => a.step_order - b.step_order);

  const handleAddStep = async () => {
    if (!selectedTemplateId) return;
    const nextOrder = sortedSteps.length > 0
      ? Math.max(...sortedSteps.map(s => s.step_order)) + 1
      : 1;
    await onAddStep(Number(selectedTemplateId), delayDays, nextOrder);
    setSelectedTemplateId('');
    setDelayDays(0);
  };

  const handleMoveUp = async (index: number) => {
    if (index <= 0) return;
    const step = sortedSteps[index];
    const prevStep = sortedSteps[index - 1];
    await onUpdateStep(step.id, { step_order: prevStep.step_order });
    await onUpdateStep(prevStep.id, { step_order: step.step_order });
  };

  const handleMoveDown = async (index: number) => {
    if (index >= sortedSteps.length - 1) return;
    const step = sortedSteps[index];
    const nextStep = sortedSteps[index + 1];
    await onUpdateStep(step.id, { step_order: nextStep.step_order });
    await onUpdateStep(nextStep.id, { step_order: step.step_order });
  };

  const getTemplateName = (templateId: number) => {
    const template = templates.find(t => t.id === templateId);
    return template?.name || `Template #${templateId}`;
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-900">Campaign Sequence</h3>

      {/* Step list */}
      {sortedSteps.length === 0 ? (
        <div className="text-center py-6 text-sm text-gray-500 bg-gray-50 rounded-lg">
          No steps defined. Add steps below to build your email sequence.
        </div>
      ) : (
        <div className="space-y-2">
          {sortedSteps.map((step, index) => (
            <div
              key={step.id}
              className="flex items-center gap-3 p-3 bg-white border rounded-lg hover:shadow-sm"
            >
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-sm font-medium">
                {index + 1}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {getTemplateName(step.template_id)}
                </p>
                <p className="text-xs text-gray-500">
                  {step.delay_days === 0
                    ? 'Send immediately'
                    : `Wait ${step.delay_days} day${step.delay_days > 1 ? 's' : ''}`}
                </p>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleMoveUp(index)}
                  disabled={index === 0 || isLoading}
                  className="p-1 rounded hover:bg-gray-100 disabled:opacity-30"
                  title="Move up"
                >
                  <ArrowUpIcon className="h-4 w-4 text-gray-500" />
                </button>
                <button
                  onClick={() => handleMoveDown(index)}
                  disabled={index === sortedSteps.length - 1 || isLoading}
                  className="p-1 rounded hover:bg-gray-100 disabled:opacity-30"
                  title="Move down"
                >
                  <ArrowDownIcon className="h-4 w-4 text-gray-500" />
                </button>
                <button
                  onClick={() => onDeleteStep(step.id)}
                  disabled={isLoading}
                  className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500"
                  title="Remove step"
                >
                  <TrashIcon className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add step form */}
      <div className="border-t pt-4">
        <h4 className="text-xs font-medium text-gray-700 mb-2">Add Step</h4>
        <div className="flex flex-col sm:flex-row gap-2">
          <select
            value={selectedTemplateId}
            onChange={(e) => setSelectedTemplateId(e.target.value ? Number(e.target.value) : '')}
            className="flex-1 rounded-md border-gray-300 text-sm shadow-sm focus:border-primary-500 focus:ring-primary-500"
          >
            <option value="">Select template...</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <input
            type="number"
            min={0}
            value={delayDays}
            onChange={(e) => setDelayDays(parseInt(e.target.value) || 0)}
            className="w-24 rounded-md border-gray-300 text-sm shadow-sm focus:border-primary-500 focus:ring-primary-500"
            placeholder="Days"
            title="Delay in days"
          />
          <Button
            size="sm"
            onClick={handleAddStep}
            disabled={!selectedTemplateId || isLoading}
            leftIcon={<PlusIcon className="h-4 w-4" />}
          >
            Add
          </Button>
        </div>
      </div>
    </div>
  );
}

export default CampaignStepBuilder;

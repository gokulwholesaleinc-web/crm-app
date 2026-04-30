/**
 * Campaign step builder — list of ordered steps in an email sequence.
 *
 * Reorder uses dnd-kit + an atomic PUT /steps/order on commit. The
 * old up/down arrow buttons remain for keyboard / no-drag fallback,
 * but they now also go through the atomic-reorder path so adjacent
 * swaps don't briefly flash inconsistent state.
 */

import { useState } from 'react';
import {
  ArrowUpIcon,
  ArrowDownIcon,
  TrashIcon,
  PlusIcon,
  Bars3Icon,
} from '@heroicons/react/24/outline';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Button } from '../../../components/ui/Button';
import type { EmailCampaignStep, EmailTemplate } from '../../../types';

interface CampaignStepBuilderProps {
  steps: EmailCampaignStep[];
  templates: EmailTemplate[];
  onAddStep: (templateId: number, delayDays: number, stepOrder: number) => Promise<void>;
  onReorderSteps: (stepIds: number[]) => Promise<void>;
  onDeleteStep: (stepId: number) => Promise<void>;
  isLoading?: boolean;
}

interface SortableStepRowProps {
  step: EmailCampaignStep;
  index: number;
  total: number;
  templateName: string;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onDelete: () => void;
  isLoading: boolean;
}

function SortableStepRow({
  step,
  index,
  total,
  templateName,
  onMoveUp,
  onMoveDown,
  onDelete,
  isLoading,
}: SortableStepRowProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: step.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-3 p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:shadow-sm"
    >
      {/* Drag handle — separate from the row so the entire card isn't
          a drag target (clicking the trash button shouldn't start a
          drag). */}
      <button
        type="button"
        {...attributes}
        {...listeners}
        className="flex-shrink-0 p-1 -ml-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 cursor-grab active:cursor-grabbing focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-500 rounded"
        aria-label={`Drag to reorder step ${index + 1}`}
        title="Drag to reorder"
      >
        <Bars3Icon className="h-4 w-4" />
      </button>
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 flex items-center justify-center text-sm font-medium tabular-nums">
        {index + 1}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
          {templateName}
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {step.delay_days === 0
            ? 'Send immediately'
            : `Wait ${step.delay_days} day${step.delay_days > 1 ? 's' : ''}`}
        </p>
      </div>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onMoveUp}
          disabled={index === 0 || isLoading}
          className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30"
          title="Move up"
          aria-label={`Move step ${index + 1} up`}
        >
          <ArrowUpIcon className="h-4 w-4 text-gray-500 dark:text-gray-400" />
        </button>
        <button
          type="button"
          onClick={onMoveDown}
          disabled={index === total - 1 || isLoading}
          className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-30"
          title="Move down"
          aria-label={`Move step ${index + 1} down`}
        >
          <ArrowDownIcon className="h-4 w-4 text-gray-500 dark:text-gray-400" />
        </button>
        <button
          type="button"
          onClick={onDelete}
          disabled={isLoading}
          className="p-1 rounded hover:bg-red-50 dark:hover:bg-red-900/20 text-gray-400 hover:text-red-500 dark:hover:text-red-400"
          title="Remove step"
          aria-label={`Remove step ${index + 1}`}
        >
          <TrashIcon className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

export function CampaignStepBuilder({
  steps,
  templates,
  onAddStep,
  onReorderSteps,
  onDeleteStep,
  isLoading,
}: CampaignStepBuilderProps) {
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | ''>('');
  const [delayDays, setDelayDays] = useState<number>(0);

  const sortedSteps = steps.toSorted((a, b) => a.step_order - b.step_order);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleAddStep = async () => {
    if (!selectedTemplateId) return;
    const nextOrder =
      sortedSteps.length > 0
        ? Math.max(...sortedSteps.map((s) => s.step_order)) + 1
        : 1;
    await onAddStep(Number(selectedTemplateId), delayDays, nextOrder);
    setSelectedTemplateId('');
    setDelayDays(0);
  };

  const reorderTo = async (newOrder: EmailCampaignStep[]) => {
    const ids = newOrder.map((s) => s.id);
    await onReorderSteps(ids);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const fromIndex = sortedSteps.findIndex((s) => s.id === active.id);
    const toIndex = sortedSteps.findIndex((s) => s.id === over.id);
    if (fromIndex === -1 || toIndex === -1) return;
    const next = arrayMove(sortedSteps, fromIndex, toIndex);
    await reorderTo(next);
  };

  const handleMoveUp = async (index: number) => {
    if (index <= 0) return;
    const next = arrayMove(sortedSteps, index, index - 1);
    await reorderTo(next);
  };

  const handleMoveDown = async (index: number) => {
    if (index >= sortedSteps.length - 1) return;
    const next = arrayMove(sortedSteps, index, index + 1);
    await reorderTo(next);
  };

  const getTemplateName = (templateId: number) => {
    const template = templates.find((t) => t.id === templateId);
    return template?.name || `Template #${templateId}`;
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
        Campaign Sequence
      </h3>

      {sortedSteps.length === 0 ? (
        <div className="text-center py-6 text-sm text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
          No steps defined. Add steps below to build your email sequence.
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={sortedSteps.map((s) => s.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-2">
              {sortedSteps.map((step, index) => (
                <SortableStepRow
                  key={step.id}
                  step={step}
                  index={index}
                  total={sortedSteps.length}
                  templateName={getTemplateName(step.template_id)}
                  onMoveUp={() => handleMoveUp(index)}
                  onMoveDown={() => handleMoveDown(index)}
                  onDelete={() => onDeleteStep(step.id)}
                  isLoading={!!isLoading}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      {/* Add step form */}
      <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
        <h4 className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
          Add Step
        </h4>
        <div className="flex flex-col sm:flex-row gap-2">
          <select
            value={selectedTemplateId}
            onChange={(e) =>
              setSelectedTemplateId(e.target.value ? Number(e.target.value) : '')
            }
            className="flex-1 rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 text-sm shadow-sm focus:border-primary-500 focus:ring-primary-500"
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
            className="w-24 rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 text-sm shadow-sm focus:border-primary-500 focus:ring-primary-500"
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

import { useState, useCallback, useMemo } from 'react';
import {
  DndContext,
  DragOverlay,
  DragStartEvent,
  DragEndEvent,
  DragOverEvent,
  closestCorners,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useDroppable } from '@dnd-kit/core';
import clsx from 'clsx';
import { useLeadKanban, useMoveLeadStage } from '../../../hooks/useLeads';
import type { KanbanLead, KanbanLeadStage } from '../../../types';
import { getScoreColor } from '../../../utils';

// Lead Card Component

interface LeadCardProps {
  lead: KanbanLead;
  onClick?: () => void;
}

function LeadCard({ lead, onClick }: LeadCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: `lead-${lead.id}`,
    data: {
      type: 'lead',
      lead,
    },
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={onClick}
      className={clsx(
        'bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-3 sm:p-4 cursor-grab active:cursor-grabbing touch-manipulation',
        'hover:shadow-md transition-shadow duration-200',
        isDragging && 'opacity-50 shadow-lg'
      )}
    >
      <div className="space-y-2">
        {/* Lead Name */}
        <div>
          <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-1">
            {lead.full_name}
          </h4>
          {lead.company_name && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">
              {lead.company_name}
            </p>
          )}
        </div>

        {/* Email */}
        {lead.email && (
          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
            {lead.email}
          </p>
        )}

        {/* Score Badge */}
        <div className="flex items-center justify-between pt-1">
          <div className="flex items-center gap-1.5">
            <div className="w-12 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className={clsx('h-full rounded-full', {
                  'bg-green-500': lead.score >= 80,
                  'bg-yellow-500': lead.score >= 60 && lead.score < 80,
                  'bg-orange-500': lead.score >= 40 && lead.score < 60,
                  'bg-red-500': lead.score < 40,
                })}
                style={{ width: `${Math.min(100, Math.max(0, lead.score))}%` }}
              />
            </div>
            <span className={clsx('text-xs font-medium', getScoreColor(lead.score))}>
              {lead.score}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// Lead Column Component

interface LeadColumnProps {
  stage: KanbanLeadStage;
  leads: Array<KanbanLead & { _stageId: number }>;
  onLeadClick?: (lead: KanbanLead) => void;
}

function LeadColumn({ stage, leads, onLeadClick }: LeadColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: `stage-${stage.stage_id}`,
    data: {
      type: 'column',
      stageId: stage.stage_id,
    },
  });

  return (
    <div
      className={clsx(
        'flex flex-col bg-gray-50 dark:bg-gray-900 rounded-lg min-w-[260px] max-w-[260px] sm:min-w-[300px] sm:max-w-[300px] shrink-0 snap-start sm:snap-align-none',
        isOver && 'bg-gray-100 dark:bg-gray-800'
      )}
    >
      {/* Column Header */}
      <div className="p-2 sm:p-3 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2 min-w-0">
            <div
              className="w-3 h-3 rounded-full shrink-0"
              style={{ backgroundColor: stage.color }}
            />
            <h3 className="font-medium text-gray-900 dark:text-gray-100 text-sm sm:text-base truncate">
              {stage.stage_name}
            </h3>
            <span className="inline-flex items-center justify-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 shrink-0">
              {stage.count}
            </span>
          </div>
        </div>
        <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 mt-1">
          {stage.probability}% probability
        </p>
      </div>

      {/* Column Content */}
      <div
        ref={setNodeRef}
        className="flex-1 p-2 space-y-2 overflow-y-auto min-h-[150px] sm:min-h-[200px] max-h-[60vh] sm:max-h-[70vh]"
      >
        <SortableContext
          items={leads.map((l) => `lead-${l.id}`)}
          strategy={verticalListSortingStrategy}
        >
          {leads.map((lead) => (
            <LeadCard
              key={lead.id}
              lead={lead}
              onClick={() => onLeadClick?.(lead)}
            />
          ))}
        </SortableContext>

        {leads.length === 0 && (
          <div className="flex items-center justify-center h-24 sm:h-32 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg">
            <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
              Drop leads here
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// Lead Kanban Board

interface LeadKanbanBoardProps {
  onLeadClick?: (lead: KanbanLead) => void;
}

export function LeadKanbanBoard({ onLeadClick }: LeadKanbanBoardProps) {
  const { data: kanbanData, isLoading, error } = useLeadKanban();
  const moveLeadMutation = useMoveLeadStage();
  const [activeLead, setActiveLead] = useState<KanbanLead | null>(null);
  const [localStages, setLocalStages] = useState<KanbanLeadStage[] | null>(null);

  const stages = useMemo(
    () => localStages ?? kanbanData?.stages ?? [],
    [localStages, kanbanData]
  );

  // Sync local state when data changes
  const dataKey = JSON.stringify(kanbanData?.stages?.map((s) => `${s.stage_id}:${s.leads.map((l) => l.id).join(',')}`));
  const localKey = JSON.stringify(localStages?.map((s) => `${s.stage_id}:${s.leads.map((l) => l.id).join(',')}`));
  if (kanbanData?.stages && dataKey !== localKey && !activeLead) {
    setLocalStages(kanbanData.stages);
  }

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 },
    }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 150, tolerance: 5 },
    })
  );

  const findLeadAndStage = useCallback(
    (leadDndId: string) => {
      const leadId = parseInt(leadDndId.replace('lead-', ''));
      for (const stage of stages) {
        const lead = stage.leads.find((l) => l.id === leadId);
        if (lead) return { lead, stageId: stage.stage_id };
      }
      return null;
    },
    [stages]
  );

  const handleDragStart = (event: DragStartEvent) => {
    const result = findLeadAndStage(event.active.id as string);
    if (result) {
      setActiveLead(result.lead);
    }
  };

  const handleDragOver = (event: DragOverEvent) => {
    const { active, over } = event;
    if (!over) return;

    const activeId = active.id as string;
    const activeResult = findLeadAndStage(activeId);
    if (!activeResult) return;

    let targetStageId: number | null = null;
    const overData = over.data.current;

    if (overData?.type === 'column') {
      targetStageId = overData.stageId;
    } else {
      // Dropped on another lead card
      const overResult = findLeadAndStage(over.id as string);
      if (overResult) {
        targetStageId = overResult.stageId;
      }
    }

    if (targetStageId && targetStageId !== activeResult.stageId) {
      setLocalStages((prev) => {
        if (!prev) return prev;
        const newStages = prev.map((s) => ({ ...s, leads: [...s.leads] }));

        // Remove from old stage
        const oldStage = newStages.find((s) => s.stage_id === activeResult.stageId);
        if (oldStage) {
          oldStage.leads = oldStage.leads.filter((l) => l.id !== activeResult.lead.id);
          oldStage.count = oldStage.leads.length;
        }

        // Add to new stage
        const newStage = newStages.find((s) => s.stage_id === targetStageId);
        if (newStage && !newStage.leads.find((l) => l.id === activeResult.lead.id)) {
          newStage.leads.push(activeResult.lead);
          newStage.count = newStage.leads.length;
        }

        return newStages;
      });
    }
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveLead(null);

    if (!over) return;

    const activeId = active.id as string;
    const leadId = parseInt(activeId.replace('lead-', ''));

    // Determine target stage
    let targetStageId: number | null = null;
    const overData = over.data.current;

    if (overData?.type === 'column') {
      targetStageId = overData.stageId;
    } else {
      // Find which stage the target lead is in (from local state)
      const result = findLeadAndStage(over.id as string);
      if (result) {
        targetStageId = result.stageId;
      }
    }

    if (!targetStageId) return;

    try {
      await moveLeadMutation.mutateAsync({
        leadId,
        newStageId: targetStageId,
      });
    } catch {
      // Revert on error
      if (kanbanData?.stages) {
        setLocalStages(kanbanData.stages);
      }
    }
  };

  const handleDragCancel = () => {
    setActiveLead(null);
    if (kanbanData?.stages) {
      setLocalStages(kanbanData.stages);
    }
  };

  if (isLoading) {
    return (
      <div className="flex gap-4 overflow-x-auto pb-4">
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="min-w-[260px] sm:min-w-[300px] bg-gray-50 dark:bg-gray-900 rounded-lg h-96 animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
        <p className="text-sm text-red-800 dark:text-red-300">
          Failed to load kanban board
        </p>
      </div>
    );
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
      onDragCancel={handleDragCancel}
    >
      <div className="flex gap-3 sm:gap-4 overflow-x-auto pb-4 -mx-1 px-1 snap-x snap-mandatory sm:snap-none scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-transparent">
        {stages.map((stage) => (
          <LeadColumn
            key={stage.stage_id}
            stage={stage}
            leads={stage.leads.map((l) => ({ ...l, _stageId: stage.stage_id }))}
            onLeadClick={onLeadClick}
          />
        ))}
      </div>

      <DragOverlay>
        {activeLead && (
          <div className="rotate-3">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-3 sm:p-4 w-[260px] sm:w-[280px]">
              <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                {activeLead.full_name}
              </h4>
              {activeLead.company_name && (
                <p className="text-xs text-gray-500 mt-0.5">
                  {activeLead.company_name}
                </p>
              )}
            </div>
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}

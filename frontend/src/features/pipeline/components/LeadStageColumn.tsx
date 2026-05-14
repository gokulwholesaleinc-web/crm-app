import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import clsx from 'clsx';
import type { KanbanLeadStage } from '../../../types';
import { encodeLeadColumnId, encodeLeadDragId } from '../utils/dragIds';
import { SortableLeadCard } from './SortableLeadCard';

interface LeadStageColumnProps {
  stage: KanbanLeadStage;
  isDragging: boolean;
}

// Link Creative brand gold. Used for the active-drop ring so the user
// has a clear, on-brand affordance for "this column is the drop target".
const BRAND_GOLD = '#D4A574';

export function LeadStageColumn({ stage, isDragging }: LeadStageColumnProps) {
  const columnDragIds = stage.leads.map((l) =>
    encodeLeadDragId(l.id, stage.stage_id),
  );
  const { setNodeRef, isOver } = useDroppable({
    id: encodeLeadColumnId(stage.stage_id),
  });

  return (
    <div ref={setNodeRef} className="w-full md:flex-shrink-0 md:w-72">
      <div
        className={clsx(
          'bg-gray-50 dark:bg-gray-900/50 rounded-lg p-3 h-full transition-[box-shadow,background-color] duration-150',
          isOver && 'bg-amber-50/60 dark:bg-amber-900/20',
          isDragging && !isOver && 'ring-1 ring-dashed ring-gray-300 dark:ring-gray-600',
        )}
        // Inline ring color so it matches LC brand gold without adding a
        // bespoke Tailwind palette entry. Only painted when `isOver` so
        // it doesn't clobber the dashed-ring while dragging elsewhere.
        style={isOver ? { boxShadow: `0 0 0 2px ${BRAND_GOLD}` } : undefined}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <div
              className="w-3 h-3 rounded-full shrink-0"
              style={{ backgroundColor: stage.color }}
              aria-hidden="true"
            />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
              {stage.stage_name}
            </h3>
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0 ml-2">
            {stage.count}
          </span>
        </div>
        <SortableContext
          items={columnDragIds}
          strategy={verticalListSortingStrategy}
        >
          <div
            data-droppable-id={`lead-stage-${stage.stage_id}`}
            className="space-y-2 max-h-[calc(100vh-18rem)] overflow-y-auto min-h-[3rem]"
          >
            {stage.leads.map((lead) => (
              <SortableLeadCard
                key={lead.id}
                lead={lead}
                stageId={stage.stage_id}
              />
            ))}
            {stage.leads.length === 0 && (
              <p
                className={clsx(
                  'text-xs text-center py-6 transition-colors',
                  isOver
                    ? 'font-medium'
                    : 'text-gray-400 dark:text-gray-500',
                )}
                style={isOver ? { color: BRAND_GOLD } : undefined}
              >
                {isOver ? 'Drop here' : 'Drop leads here'}
              </p>
            )}
          </div>
        </SortableContext>
      </div>
    </div>
  );
}

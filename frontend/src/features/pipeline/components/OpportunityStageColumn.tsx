import { useNavigate } from 'react-router-dom';
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import type { KanbanStage } from '../../../types';
import { encodeOppColumnId, encodeOppDragId } from '../utils/dragIds';
import { SortableOppCard } from './SortableOppCard';
import { formatCurrency } from '../../../utils';

export function OpportunityStageColumn({
  stage,
  isDragging,
}: {
  stage: KanbanStage;
  isDragging: boolean;
}) {
  const navigate = useNavigate();
  const columnDragIds = stage.opportunities.map((o) => encodeOppDragId(o.id, stage.stage_id));
  const { setNodeRef, isOver } = useDroppable({ id: encodeOppColumnId(stage.stage_id) });

  const dropHighlight = isOver
    ? 'ring-2 ring-emerald-500 dark:ring-emerald-400 bg-emerald-100/70 dark:bg-emerald-900/40'
    : isDragging
      ? 'ring-1 ring-dashed ring-emerald-300 dark:ring-emerald-700'
      : '';

  return (
    <div ref={setNodeRef} className="w-full md:flex-shrink-0 md:w-72">
      <div
        className={`bg-emerald-50/50 dark:bg-emerald-950/30 rounded-lg p-3 h-full transition-[box-shadow,background-color] duration-150 ${dropHighlight}`}
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
          <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0 ml-2">{stage.count}</span>
        </div>
        <p
          className="text-xs text-gray-500 dark:text-gray-400 mb-3"
          style={{ fontVariantNumeric: 'tabular-nums' }}
        >
          {formatCurrency(stage.total_amount ?? 0, 'USD')}
        </p>
        <SortableContext items={columnDragIds} strategy={verticalListSortingStrategy}>
          <div
            data-droppable-id={`opp-stage-${stage.stage_id}`}
            className="space-y-2 max-h-[calc(100vh-22rem)] overflow-y-auto min-h-[3rem]"
          >
            {stage.opportunities.map((opp) => (
              <SortableOppCard
                key={opp.id}
                opportunity={opp}
                stageId={stage.stage_id}
                onClick={() => navigate(`/opportunities/${opp.id}`)}
              />
            ))}
            {stage.opportunities.length === 0 && (
              <p
                className={`text-xs text-center py-4 transition-colors ${
                  isOver
                    ? 'text-emerald-600 dark:text-emerald-400 font-medium'
                    : 'text-gray-400 dark:text-gray-500'
                }`}
              >
                {isOver ? 'Drop here' : 'No deals'}
              </p>
            )}
          </div>
        </SortableContext>
      </div>
    </div>
  );
}

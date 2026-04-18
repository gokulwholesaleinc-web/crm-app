import { useNavigate } from 'react-router-dom';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import type { KanbanLeadStage } from '../../../types';
import { encodeLeadDragId } from '../utils/dragIds';
import { SortableLeadCard } from './SortableLeadCard';

export function LeadStageColumn({ stage }: { stage: KanbanLeadStage }) {
  const navigate = useNavigate();
  const columnDragIds = stage.leads.map((l) => encodeLeadDragId(l.id, stage.stage_id));
  return (
    <div className="w-full md:flex-shrink-0 md:w-72">
      <div className="bg-blue-50/50 dark:bg-blue-950/30 rounded-lg p-3 h-full">
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
        <SortableContext items={columnDragIds} strategy={verticalListSortingStrategy}>
          <div
            data-droppable-id={`lead-stage-${stage.stage_id}`}
            className="space-y-2 max-h-[calc(100vh-22rem)] overflow-y-auto"
          >
            {stage.leads.map((lead) => (
              <SortableLeadCard
                key={lead.id}
                lead={lead}
                stageId={stage.stage_id}
                onClick={() => navigate(`/leads/${lead.id}`)}
              />
            ))}
            {stage.leads.length === 0 && (
              <p className="text-xs text-gray-400 dark:text-gray-500 text-center py-4">No leads</p>
            )}
          </div>
        </SortableContext>
      </div>
    </div>
  );
}

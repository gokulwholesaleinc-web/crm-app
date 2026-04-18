import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { KanbanLead } from '../../../types';
import { encodeLeadDragId } from '../utils/dragIds';

export function SortableLeadCard({
  lead,
  stageId,
  onClick,
}: {
  lead: KanbanLead;
  stageId: number;
  onClick: () => void;
}) {
  const dragId = encodeLeadDragId(lead.id, stageId);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: dragId,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <button
        type="button"
        onClick={onClick}
        className="w-full text-left bg-blue-50 dark:bg-blue-900/20 rounded-lg shadow-sm border border-blue-200 dark:border-blue-800 p-3 hover:shadow-md transition-shadow duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
      >
        <div className="space-y-1.5">
          <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2">
            {lead.full_name}
          </h4>
          {lead.company_name && (
            <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{lead.company_name}</p>
          )}
          {lead.email && (
            <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{lead.email}</p>
          )}
          <div className="flex items-center gap-1.5">
            <span className="inline-flex items-center rounded-full bg-blue-100 dark:bg-blue-800 px-2 py-0.5 text-xs font-medium text-blue-700 dark:text-blue-300">
              Score: {lead.score}
            </span>
          </div>
        </div>
      </button>
    </div>
  );
}

export function LeadDragOverlay({ lead }: { lead: KanbanLead }) {
  return (
    <div className="w-72 bg-blue-50 dark:bg-blue-900/20 rounded-lg shadow-lg border border-blue-200 dark:border-blue-800 p-3 rotate-2 opacity-90">
      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2">
        {lead.full_name}
      </h4>
      {lead.company_name && (
        <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-1">{lead.company_name}</p>
      )}
    </div>
  );
}

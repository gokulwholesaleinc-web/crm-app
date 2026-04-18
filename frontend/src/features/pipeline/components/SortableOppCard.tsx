import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { KanbanOpportunity } from '../../../types';
import { encodeOppDragId } from '../utils/dragIds';
import { formatCurrency } from '../../../utils';

export function SortableOppCard({
  opportunity,
  stageId,
  onClick,
}: {
  opportunity: KanbanOpportunity;
  stageId: number;
  onClick: () => void;
}) {
  const dragId = encodeOppDragId(opportunity.id, stageId);
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
        className="w-full text-left bg-emerald-50 dark:bg-emerald-900/20 rounded-lg shadow-sm border border-emerald-200 dark:border-emerald-800 p-3 hover:shadow-md transition-shadow duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
      >
        <div className="space-y-1.5">
          <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2">
            {opportunity.name}
          </h4>
          {opportunity.company_name && (
            <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
              {opportunity.company_name}
            </p>
          )}
          <div className="flex items-center justify-between gap-2">
            <span
              className="text-sm font-semibold text-gray-900 dark:text-gray-100"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {formatCurrency(opportunity.amount ?? 0, opportunity.currency)}
            </span>
          </div>
          {opportunity.contact_name && (
            <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
              <svg
                className="h-3.5 w-3.5 shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                />
              </svg>
              <span className="truncate">{opportunity.contact_name}</span>
            </div>
          )}
        </div>
      </button>
    </div>
  );
}

export function OppDragOverlay({ opp }: { opp: KanbanOpportunity }) {
  return (
    <div className="w-72 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg shadow-lg border border-emerald-200 dark:border-emerald-800 p-3 rotate-2 opacity-90">
      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2">{opp.name}</h4>
      <span
        className="text-sm font-semibold text-gray-900 dark:text-gray-100"
        style={{ fontVariantNumeric: 'tabular-nums' }}
      >
        {formatCurrency(opp.amount ?? 0, opp.currency)}
      </span>
    </div>
  );
}

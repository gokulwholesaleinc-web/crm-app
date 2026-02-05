import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import clsx from 'clsx';
import { formatCurrency, formatDate } from '../../../../utils/formatters';

export interface Opportunity {
  id: string;
  name: string;
  value: number;
  stage: string;
  probability: number;
  expectedCloseDate?: string;
  contactName?: string;
  companyName?: string;
}

interface KanbanCardProps {
  opportunity: Opportunity;
  onClick?: () => void;
}

export function KanbanCard({ opportunity, onClick }: KanbanCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: opportunity.id,
    data: {
      type: 'opportunity',
      opportunity,
    },
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const isOverdue =
    opportunity.expectedCloseDate &&
    new Date(opportunity.expectedCloseDate) < new Date();

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={onClick}
      className={clsx(
        'bg-white rounded-lg shadow-sm border border-gray-200 p-4 cursor-grab active:cursor-grabbing',
        'hover:shadow-md transition-shadow duration-200',
        isDragging && 'opacity-50 shadow-lg'
      )}
    >
      <div className="space-y-3">
        {/* Opportunity Name */}
        <div>
          <h4 className="text-sm font-medium text-gray-900 line-clamp-2">
            {opportunity.name}
          </h4>
          {opportunity.companyName && (
            <p className="text-xs text-gray-500 mt-0.5">
              {opportunity.companyName}
            </p>
          )}
        </div>

        {/* Value */}
        <div className="flex items-center justify-between">
          <span className="text-lg font-semibold text-gray-900">
            {formatCurrency(opportunity.value)}
          </span>
          <span className="text-xs text-gray-500">
            {opportunity.probability}% probability
          </span>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-2 border-t border-gray-100">
          {/* Contact */}
          {opportunity.contactName && (
            <div className="flex items-center space-x-1">
              <svg
                className="h-4 w-4 text-gray-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
                />
              </svg>
              <span className="text-xs text-gray-500 truncate max-w-20">
                {opportunity.contactName}
              </span>
            </div>
          )}

          {/* Close Date */}
          {opportunity.expectedCloseDate && (
            <div
              className={clsx(
                'flex items-center space-x-1',
                isOverdue ? 'text-red-600' : 'text-gray-500'
              )}
            >
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
                />
              </svg>
              <span className="text-xs">
                {formatDate(opportunity.expectedCloseDate, 'short')}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

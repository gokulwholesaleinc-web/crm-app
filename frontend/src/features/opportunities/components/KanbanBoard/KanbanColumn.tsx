import { useDroppable } from '@dnd-kit/core';
import {
  SortableContext,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import clsx from 'clsx';
import { KanbanCard, Opportunity } from './KanbanCard';
import { formatCurrency } from '../../../../utils/formatters';

interface KanbanColumnProps {
  id: string;
  title: string;
  opportunities: Opportunity[];
  totalValue: number;
  color?: string;
  onOpportunityClick?: (opportunity: Opportunity) => void;
}

export function KanbanColumn({
  id,
  title,
  opportunities,
  totalValue,
  color = 'gray',
  onOpportunityClick,
}: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id,
    data: {
      type: 'column',
      stage: id,
    },
  });

  const colorClasses: Record<string, string> = {
    blue: 'bg-blue-500',
    yellow: 'bg-yellow-500',
    purple: 'bg-purple-500',
    orange: 'bg-orange-500',
    green: 'bg-green-500',
    red: 'bg-red-500',
    gray: 'bg-gray-500',
  };

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
              className={clsx('w-3 h-3 rounded-full shrink-0', colorClasses[color])}
            />
            <h3 className="font-medium text-gray-900 dark:text-gray-100 text-sm sm:text-base truncate">{title}</h3>
            <span className="inline-flex items-center justify-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 shrink-0">
              {opportunities.length}
            </span>
          </div>
        </div>
        <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 mt-1">
          {formatCurrency(totalValue)}
        </p>
      </div>

      {/* Column Content */}
      <div
        ref={setNodeRef}
        className="flex-1 p-2 space-y-2 overflow-y-auto min-h-[150px] sm:min-h-[200px] max-h-[60vh] sm:max-h-[70vh]"
      >
        <SortableContext
          items={opportunities.map((o) => o.id)}
          strategy={verticalListSortingStrategy}
        >
          {opportunities.map((opportunity) => (
            <KanbanCard
              key={opportunity.id}
              opportunity={opportunity}
              onClick={() => onOpportunityClick?.(opportunity)}
            />
          ))}
        </SortableContext>

        {opportunities.length === 0 && (
          <div className="flex items-center justify-center h-24 sm:h-32 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg">
            <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">Drop opportunities here</p>
          </div>
        )}
      </div>
    </div>
  );
}

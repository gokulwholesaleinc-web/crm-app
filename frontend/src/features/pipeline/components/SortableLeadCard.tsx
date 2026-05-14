import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useNavigate } from 'react-router-dom';
import type { KanbanLead } from '../../../types';
import { useAuthStore } from '../../../store/authStore';
import { encodeLeadDragId } from '../utils/dragIds';

interface SortableLeadCardProps {
  lead: KanbanLead;
  stageId: number;
}

export function SortableLeadCard({ lead, stageId }: SortableLeadCardProps) {
  const navigate = useNavigate();
  const dragId = encodeLeadDragId(lead.id, stageId);
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: dragId });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  // Owner pill is only useful for managers/admins who see other reps'
  // leads. Sales reps see only their own pipeline so the pill is noise.
  const role = useAuthStore((s) => s.user?.role);
  const showOwner =
    (role === 'admin' || role === 'manager') && !!lead.owner_name;

  // Initials for the avatar bubble. Falls back to the first character of
  // full_name so reps with no owner_name still render something legible
  // rather than an empty circle.
  const ownerInitials = lead.owner_name
    ? lead.owner_name
        .split(' ')
        .map((s) => s[0])
        .filter(Boolean)
        .slice(0, 2)
        .join('')
        .toUpperCase()
    : null;

  // The wrapper carries dnd-kit's pointer listeners and the explicit
  // button below handles navigation — PointerSensor's 5px activation
  // distance lets a tap-without-drag pass through to the button.
  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-3 hover:shadow-md transition-shadow duration-150 cursor-grab active:cursor-grabbing"
    >
      <div className="space-y-1.5">
        <button
          type="button"
          onClick={(e) => {
            // Card-level drag listeners would otherwise swallow the
            // click. Stop propagation so the navigate fires cleanly.
            e.stopPropagation();
            navigate(`/leads/${lead.id}`);
          }}
          className="text-sm font-medium text-gray-900 dark:text-gray-100 hover:text-primary-600 dark:hover:text-primary-300 line-clamp-2 text-left focus-visible:outline-none focus-visible:underline"
        >
          {lead.full_name || 'Unnamed lead'}
        </button>
        {lead.company_name && (
          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
            {lead.company_name}
          </p>
        )}
        {lead.email && (
          <p className="text-xs text-gray-400 dark:text-gray-500 truncate">
            {lead.email}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          <span className="inline-flex items-center rounded-full bg-primary-50 dark:bg-primary-900/30 px-2 py-0.5 text-xs font-medium text-primary-700 dark:text-primary-300">
            Score {lead.score}
          </span>
          {showOwner && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-gray-100 dark:bg-gray-700 px-2 py-0.5 text-xs font-medium text-gray-600 dark:text-gray-300 max-w-[10rem]"
              title={`Owner: ${lead.owner_name}`}
            >
              {ownerInitials && (
                <span
                  className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-gray-300 dark:bg-gray-600 text-[10px] font-semibold text-gray-700 dark:text-gray-100"
                  aria-hidden="true"
                >
                  {ownerInitials}
                </span>
              )}
              <span className="truncate">{lead.owner_name}</span>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function LeadDragOverlay({ lead }: { lead: KanbanLead }) {
  return (
    <div className="w-72 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-3 rotate-2 opacity-95">
      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2">
        {lead.full_name || 'Unnamed lead'}
      </h4>
      {lead.company_name && (
        <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-1">
          {lead.company_name}
        </p>
      )}
      <span className="inline-flex items-center mt-2 rounded-full bg-primary-50 dark:bg-primary-900/30 px-2 py-0.5 text-xs font-medium text-primary-700 dark:text-primary-300">
        Score {lead.score}
      </span>
    </div>
  );
}

import { useState, useMemo, useDeferredValue } from 'react';
import { Link } from 'react-router-dom';
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  closestCenter,
  pointerWithin,
  rectIntersection,
  type CollisionDetection,
} from '@dnd-kit/core';
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable';
import { useLeadKanban, useMoveLeadStage } from '../../hooks/useLeads';
import { useUsers } from '../../hooks/useAuth';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useAuthStore } from '../../store/authStore';
import { showSuccess } from '../../utils/toast';
import { SkeletonKanban } from '../../components/ui/Skeleton';
import { LeadStageColumn } from './components/LeadStageColumn';
import { LeadDragOverlay } from './components/SortableLeadCard';
import {
  encodeLeadColumnId,
  encodeLeadDragId,
  parseLeadDragId,
} from './utils/dragIds';

function PipelinePage() {
  usePageTitle('Pipeline');

  const role = useAuthStore((s) => s.user?.role);
  const isManagerOrAdmin = role === 'admin' || role === 'manager';

  const [ownerFilter, setOwnerFilter] = useState<number | undefined>(undefined);
  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  // Deferred so typing on a large board doesn't block the per-column
  // filter recompute on every keystroke.
  const deferredQuery = useDeferredValue(searchQuery);

  // Only managers/admins can scope the board to a specific owner — the
  // backend already filters reps to their own leads, so the picker
  // would be a no-op for them.
  const { data: usersData } = useUsers(0, 100, { enabled: isManagerOrAdmin });

  const { data: kanban, isLoading, error } = useLeadKanban(ownerFilter);
  const moveLead = useMoveLeadStage();

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  // Forgiving collision detection: pointer-within wins (any droppable
  // under the cursor), then rectangle intersection, then closest-center
  // as a final fallback. This is what makes "good enough" drops land.
  const collisionDetection: CollisionDetection = (args) => {
    const pointerHits = pointerWithin(args);
    if (pointerHits.length > 0) return pointerHits;
    const rectHits = rectIntersection(args);
    if (rectHits.length > 0) return rectHits;
    return closestCenter(args);
  };

  // Apply the search filter in-memory so dragging keeps working —
  // every visible card still has a real backend stage. Counts are
  // recomputed off the filtered list so column headers reflect what
  // the user can actually see.
  const { stages, totalCount, filteredCount } = useMemo(() => {
    const rawStages = kanban?.stages ?? [];
    const totalCount = rawStages.reduce((sum, s) => sum + (s.count ?? 0), 0);
    const needle = deferredQuery.trim().toLowerCase();
    if (!needle) {
      return {
        stages: rawStages,
        totalCount,
        filteredCount: totalCount,
      };
    }
    const matchLead = (l: (typeof rawStages)[number]['leads'][number]) =>
      [l.full_name, l.email, l.company_name].some(
        (f) => f && f.toLowerCase().includes(needle),
      );
    let filteredCount = 0;
    const filtered = rawStages.map((s) => {
      const leads = s.leads.filter(matchLead);
      filteredCount += leads.length;
      return { ...s, leads, count: leads.length };
    });
    return { stages: filtered, totalCount, filteredCount };
  }, [kanban?.stages, deferredQuery]);

  // Drag overlay uses the un-filtered set to look up the active card —
  // a drag-then-type race could otherwise blank the overlay.
  const leadById = useMemo(() => {
    return new Map(
      (kanban?.stages ?? []).flatMap((s) => s.leads.map((l) => [l.id, l])),
    );
  }, [kanban?.stages]);

  // Stage lookup keyed by drag id — includes both per-card and per-column
  // ids so dropping on the column body works the same as dropping on
  // another card.
  const stageByDragId = useMemo(() => {
    const m = new Map<string, number>();
    for (const s of stages) {
      for (const l of s.leads) {
        m.set(encodeLeadDragId(l.id, s.stage_id), s.stage_id);
      }
      m.set(encodeLeadColumnId(s.stage_id), s.stage_id);
    }
    return m;
  }, [stages]);

  const handleDragStart = (event: DragStartEvent) => {
    setActiveDragId(String(event.active.id));
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveDragId(null);
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const activeId = String(active.id);
    const overId = String(over.id);

    const info = parseLeadDragId(activeId);
    if (!info) return;

    // Race guard: user drags a card, types in the search, the card
    // gets filtered out from the rendered set, dnd-kit still fires
    // onDragEnd against the stale encoded id. parseLeadDragId is a
    // pure regex so it succeeds against the stale id — verify the
    // lead still exists in our backing data before firing the move.
    if (!leadById.has(info.leadId)) return;

    const targetStageId = stageByDragId.get(overId);
    if (targetStageId == null || targetStageId === info.stageId) return;

    moveLead.mutate(
      { leadId: info.leadId, newStageId: targetStageId },
      {
        onSuccess: (data) => {
          if (data.conversion?.converted && data.conversion.contact_id) {
            showSuccess(
              `Lead converted to Contact — view at /contacts/${data.conversion.contact_id}`,
            );
          }
        },
      },
    );
  };

  const isFiltering = deferredQuery.trim() !== '';
  const activeLead = activeDragId
    ? (() => {
        const parsed = parseLeadDragId(activeDragId);
        return parsed ? (leadById.get(parsed.leadId) ?? null) : null;
      })()
    : null;
  const isDragging = activeLead !== null;

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">
            Pipeline
          </h1>
          <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            Track leads across your sales pipeline. New leads stay
            off-board until you promote them.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Link
            to="/leads"
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
          >
            Back to Leads
          </Link>
        </div>
      </div>

      {/* Toolbar */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-3 sm:p-4 border border-transparent dark:border-gray-700">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
          <div className="flex-1 min-w-0">
            <label htmlFor="pipeline-search" className="sr-only">
              Search pipeline
            </label>
            <input
              id="pipeline-search"
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by name, email, or company..."
              className="block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500 focus-visible:border-primary-500"
              spellCheck={false}
            />
          </div>
          {isManagerOrAdmin && (
            <div className="sm:w-56">
              <label htmlFor="pipeline-owner" className="sr-only">
                Filter by owner
              </label>
              <select
                id="pipeline-owner"
                value={ownerFilter ?? ''}
                onChange={(e) => {
                  const v = e.target.value;
                  setOwnerFilter(v === '' ? undefined : Number(v));
                }}
                className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm px-3 py-2 text-sm focus-visible:border-primary-500 focus-visible:ring-primary-500"
              >
                <option value="">All owners</option>
                {(usersData ?? []).map((u: { id: number; full_name: string }) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap" aria-live="polite">
            {isFiltering
              ? `${filteredCount} of ${totalCount} match`
              : `${totalCount} lead${totalCount === 1 ? '' : 's'} on board`}
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4" role="alert">
          <p className="text-sm text-red-800 dark:text-red-300">
            {error instanceof Error
              ? error.message
              : 'Failed to load pipeline.'}
          </p>
        </div>
      )}

      {/* Kanban */}
      {isLoading ? (
        <SkeletonKanban columns={6} />
      ) : stages.length === 0 ? (
        <div className="text-center py-16 px-4 bg-white dark:bg-gray-800 rounded-lg shadow border border-transparent dark:border-gray-700">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            No pipeline stages configured
          </h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Ask an admin to seed the lead pipeline stages.
          </p>
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={collisionDetection}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
          onDragCancel={() => setActiveDragId(null)}
        >
          <div
            className="flex flex-col md:flex-row gap-3 md:gap-4 md:overflow-x-auto pb-2"
            // Prevent overscroll-y on horizontal kanban scroll from
            // bouncing the page on touch devices.
            style={{ overscrollBehavior: 'contain' }}
          >
            {stages.map((stage) => (
              <LeadStageColumn
                key={stage.stage_id}
                stage={stage}
                isDragging={isDragging}
              />
            ))}
          </div>
          <DragOverlay dropAnimation={null}>
            {activeLead ? <LeadDragOverlay lead={activeLead} /> : null}
          </DragOverlay>
        </DndContext>
      )}

      {/* Footer hint when board is empty but stages exist */}
      {!isLoading && stages.length > 0 && totalCount === 0 && (
        <p className="text-center text-sm text-gray-500 dark:text-gray-400">
          New leads stay off-board until you promote them from the Leads list.
        </p>
      )}
    </div>
  );
}

export default PipelinePage;

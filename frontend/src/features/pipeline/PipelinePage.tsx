import { useState, useMemo, useDeferredValue } from 'react';
import { useNavigate } from 'react-router-dom';
import { PlusIcon } from '@heroicons/react/24/outline';
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
import {
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import { Button, EntityLink, Spinner, Modal } from '../../components/ui';
import { OpportunityForm, OpportunityFormData } from '../opportunities/components/OpportunityForm';
import { useLeadKanban, useMoveLeadStage } from '../../hooks/useLeads';
import {
  useOpportunities,
  useKanban,
  useMoveOpportunity,
  useCreateOpportunity,
  useUpdateOpportunity,
} from '../../hooks/useOpportunities';
import { useContacts } from '../../hooks/useContacts';
import { useCompanies } from '../../hooks/useCompanies';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  formatCurrency,
  formatDate,
  formatPercentage,
  getStatusBadgeClasses,
} from '../../utils';
import { showError, showInfo } from '../../utils/toast';
import type {
  Opportunity,
  OpportunityCreate,
  OpportunityUpdate,
} from '../../types';
import {
  encodeLeadColumnId,
  encodeLeadDragId,
  encodeOppColumnId,
  encodeOppDragId,
  parseLeadDragId,
  parseOppDragId,
} from './utils/dragIds';
import { LeadDragOverlay } from './components/SortableLeadCard';
import { OppDragOverlay } from './components/SortableOppCard';
import { LeadStageColumn } from './components/LeadStageColumn';
import { OpportunityStageColumn } from './components/OpportunityStageColumn';

// ---------------------------------------------------------------------------
// Main Pipeline Page
// ---------------------------------------------------------------------------

function PipelinePage() {
  usePageTitle('Pipeline');
  const navigate = useNavigate();

  const [viewMode, setViewMode] = useState<'kanban' | 'list'>(() =>
    window.matchMedia('(min-width: 768px)').matches ? 'kanban' : 'list'
  );
  const [showForm, setShowForm] = useState(false);
  const [editingOpportunity, setEditingOpportunity] = useState<Opportunity | null>(null);
  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  // useDeferredValue keeps the input snappy on large boards — typing
  // doesn't block the filter/render of every column on every keystroke.
  const deferredQuery = useDeferredValue(searchQuery);

  const { data: leadKanban, isLoading: leadsLoading, error: leadsError } = useLeadKanban();
  const { data: oppKanban, isLoading: oppsLoading, error: oppsError } = useKanban();
  const { data: opportunitiesData, isLoading: listLoading } = useOpportunities();

  const isModalOpen = showForm || !!editingOpportunity;
  const { data: contactsData } = useContacts({ page_size: 25 }, { enabled: isModalOpen });
  const { data: companiesData } = useCompanies({ page_size: 25 }, { enabled: isModalOpen });

  const createOpportunityMutation = useCreateOpportunity();
  const updateOpportunityMutation = useUpdateOpportunity();
  const moveOpp = useMoveOpportunity();
  const moveLead = useMoveLeadStage();

  const isLoading = viewMode === 'kanban' ? leadsLoading || oppsLoading : listLoading;
  const error = leadsError || oppsError;

  // Apply the search filter in-memory so dragging keeps working — every
  // visible card still has a real backend stage to move within. We
  // recompute stage-level count + total_amount over the filtered list
  // so the column headers reflect what the user can actually see.
  //
  // Summary tiles (totalPipelineValue / openDeals / totalLeadsInPipeline)
  // read off the UNFILTERED stages so the headline figures keep their
  // dashboard semantics — searching narrows the columns, not the
  // executive summary at the top of the page. The "X of Y match" hint
  // next to the search input is the affordance for filtered counts.
  //
  // Read .stages off the React Query data INSIDE useMemo. Reading
  // outside via `oppKanban?.stages ?? []` would mint a fresh `[]` on
  // every render in the no-data path, busting the memo deps and
  // re-running the filter even when the search hadn't changed.
  const {
    leadStages,
    oppStages,
    totalPipelineValue,
    openDeals,
    totalLeadsInPipeline,
    filteredLeadCount,
    filteredOppCount,
  } = useMemo(() => {
    const rawLeadStages = leadKanban?.stages ?? [];
    const rawOppStages = oppKanban?.stages ?? [];
    const totalPipelineValue = rawOppStages.reduce((sum, s) => sum + (s.total_amount ?? 0), 0);
    const openDeals = rawOppStages.reduce((sum, s) => sum + (s.count ?? 0), 0);
    const totalLeadsInPipeline = rawLeadStages.reduce((sum, s) => sum + (s.count ?? 0), 0);

    const needle = deferredQuery.trim().toLowerCase();
    if (!needle) {
      return {
        leadStages: rawLeadStages,
        oppStages: rawOppStages,
        totalPipelineValue,
        openDeals,
        totalLeadsInPipeline,
        filteredLeadCount: totalLeadsInPipeline,
        filteredOppCount: openDeals,
      };
    }

    const matchLead = (l: (typeof rawLeadStages)[number]['leads'][number]) =>
      [l.full_name, l.email, l.company_name]
        .some((f) => f && f.toLowerCase().includes(needle));
    const matchOpp = (o: (typeof rawOppStages)[number]['opportunities'][number]) =>
      [o.name, o.company_name, o.contact_name]
        .some((f) => f && f.toLowerCase().includes(needle));

    let filteredLeadCount = 0;
    const leadStages = rawLeadStages.map((s) => {
      const leads = s.leads.filter(matchLead);
      filteredLeadCount += leads.length;
      return { ...s, leads, count: leads.length };
    });
    let filteredOppCount = 0;
    const oppStages = rawOppStages.map((s) => {
      const opportunities = s.opportunities.filter(matchOpp);
      filteredOppCount += opportunities.length;
      // Recompute the column-header total over the filtered subset, but
      // ONLY when every visible amount is a finite number — drizzle/orm
      // numeric columns can come over the wire as strings (see the
      // wholesale Decimal-string incident in memory). If we can't trust
      // the data, fall back to the backend's pre-filter total instead
      // of rendering "$01500.001500.00" garbage from string-concat.
      const allNumeric = opportunities.every(
        (o) => typeof o.amount === 'number' && Number.isFinite(o.amount),
      );
      const total_amount = allNumeric
        ? opportunities.reduce((sum, o) => sum + (o.amount ?? 0), 0)
        : (s.total_amount ?? 0);
      return { ...s, opportunities, count: opportunities.length, total_amount };
    });
    return {
      leadStages,
      oppStages,
      totalPipelineValue,
      openDeals,
      totalLeadsInPipeline,
      filteredLeadCount,
      filteredOppCount,
    };
  }, [leadKanban?.stages, oppKanban?.stages, deferredQuery]);

  const opportunityItems = opportunitiesData?.items ?? [];
  const isFiltering = deferredQuery.trim() !== '';
  const filteredCount = filteredLeadCount + filteredOppCount;
  const totalCount = totalLeadsInPipeline + openDeals;

  // Flat lookup maps used for drag overlay rendering
  const leadById = new Map(leadStages.flatMap((s) => s.leads.map((l) => [l.id, l])));
  const oppById = new Map(oppStages.flatMap((s) => s.opportunities.map((o) => [o.id, o])));

  // Stage lookup maps keyed by drag ID — used in handleDragEnd.
  // Includes both per-card IDs (for landing on a card) and per-column IDs
  // (for landing on column body / empty space).
  const leadStageByDragId = new Map<string, number>([
    ...leadStages.flatMap((s): [string, number][] =>
      s.leads.map((l) => [encodeLeadDragId(l.id, s.stage_id), s.stage_id] as [string, number])
    ),
    ...leadStages.map((s): [string, number] => [encodeLeadColumnId(s.stage_id), s.stage_id]),
  ]);
  const oppStageByDragId = new Map<string, number>([
    ...oppStages.flatMap((s): [string, number][] =>
      s.opportunities.map(
        (o) => [encodeOppDragId(o.id, s.stage_id), s.stage_id] as [string, number]
      )
    ),
    ...oppStages.map((s): [string, number] => [encodeOppColumnId(s.stage_id), s.stage_id]),
  ]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  // Forgiving collision detection: pointer-within takes priority (any droppable
  // under the cursor wins), then rectangle intersection, then closest-center as
  // a last resort. This is what makes "good enough" drops actually land.
  const collisionDetection: CollisionDetection = (args) => {
    const pointerHits = pointerWithin(args);
    if (pointerHits.length > 0) return pointerHits;
    const rectHits = rectIntersection(args);
    if (rectHits.length > 0) return rectHits;
    return closestCenter(args);
  };

  const handleDragStart = (event: DragStartEvent) => {
    setActiveDragId(String(event.active.id));
  };

  const handleDragEnd = (event: DragEndEvent) => {
    setActiveDragId(null);
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const activeId = String(active.id);
    const overId = String(over.id);

    const leadInfo = parseLeadDragId(activeId);
    if (leadInfo) {
      // Source-card existence check guards against the mid-drag-search
      // race: user drags a card, types in the search, the card gets
      // filtered out from the rendered set, dnd-kit still fires onDragEnd
      // against the original encoded id. Without this check we would
      // mutate a card the user can no longer see — silent action with
      // no UI feedback. parseLeadDragId is a pure regex so it succeeds
      // on the stale id even after the card is gone.
      if (!leadById.has(leadInfo.leadId)) return;

      const targetStageId = leadStageByDragId.get(overId) ?? null;
      if (targetStageId !== null && targetStageId !== leadInfo.stageId) {
        moveLead.mutate({ leadId: leadInfo.leadId, newStageId: targetStageId });
        return;
      }
      // Lead dropped on the opportunity side of the board. Don't silently
      // do nothing — point the user at the explicit Convert flow so they
      // can pick a contact/company and confirm. Direct lead→opp drag
      // would skip those decisions.
      const droppedOnOppColumn = oppStageByDragId.has(overId);
      if (droppedOnOppColumn) {
        showInfo(
          'To turn a lead into an opportunity, open the lead and click Convert. Dragging into the opportunity pipeline isn’t supported.',
        );
      }
      return;
    }

    const oppInfo = parseOppDragId(activeId);
    if (oppInfo) {
      // Same race guard as the lead branch above.
      if (!oppById.has(oppInfo.oppId)) return;

      const targetStageId = oppStageByDragId.get(overId) ?? null;
      if (targetStageId !== null && targetStageId !== oppInfo.stageId) {
        moveOpp.mutate({ opportunityId: oppInfo.oppId, newStageId: targetStageId });
      }
    }
  };

  const handleFormSubmit = async (data: OpportunityFormData) => {
    try {
      if (editingOpportunity) {
        const updateData: OpportunityUpdate = {
          name: data.name,
          amount: data.value,
          probability: data.probability,
          expected_close_date: data.expectedCloseDate || undefined,
          pipeline_stage_id: data.stage,
          contact_id: data.contactId ? parseInt(data.contactId, 10) : undefined,
          company_id: data.companyId ? parseInt(data.companyId, 10) : undefined,
          description: data.description,
        };
        await updateOpportunityMutation.mutateAsync({ id: editingOpportunity.id, data: updateData });
      } else {
        const createData: OpportunityCreate = {
          name: data.name,
          amount: data.value,
          currency: 'USD',
          probability: data.probability,
          expected_close_date: data.expectedCloseDate || undefined,
          pipeline_stage_id: data.stage,
          contact_id: data.contactId ? parseInt(data.contactId, 10) : undefined,
          company_id: data.companyId ? parseInt(data.companyId, 10) : undefined,
          description: data.description,
        };
        await createOpportunityMutation.mutateAsync(createData);
      }
      setShowForm(false);
      setEditingOpportunity(null);
    } catch {
      showError('Failed to save opportunity');
    }
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditingOpportunity(null);
  };

  const getInitialFormData = (): Partial<OpportunityFormData> | undefined => {
    if (!editingOpportunity) return undefined;
    return {
      name: editingOpportunity.name,
      value: editingOpportunity.amount ?? 0,
      stage: editingOpportunity.pipeline_stage_id,
      probability: editingOpportunity.probability ?? 0,
      expectedCloseDate: editingOpportunity.expected_close_date ?? '',
      contactId: editingOpportunity.contact_id ? String(editingOpportunity.contact_id) : '',
      companyId: editingOpportunity.company_id ? String(editingOpportunity.company_id) : '',
      description: editingOpportunity.description ?? '',
    };
  };

  const contactsList = (contactsData?.items ?? []).map((c) => ({
    id: String(c.id),
    name: `${c.first_name} ${c.last_name}`,
  }));

  const companiesList = (companiesData?.items ?? []).map((c) => ({
    id: String(c.id),
    name: c.name,
  }));

  const hasKanbanData = leadStages.length > 0 || oppStages.length > 0;

  const activeLead = activeDragId
    ? (() => {
        const info = parseLeadDragId(activeDragId);
        return info ? (leadById.get(info.leadId) ?? null) : null;
      })()
    : null;

  const isDraggingLead = activeLead !== null;

  const activeOpp = activeDragId
    ? (() => {
        const info = parseOppDragId(activeDragId);
        return info ? (oppById.get(info.oppId) ?? null) : null;
      })()
    : null;

  const isDraggingOpp = activeOpp !== null;

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Pipeline</h1>
          <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            Track leads and deals across all pipeline stages
          </p>
        </div>
        <div className="flex items-center justify-between sm:justify-end gap-3">
          <div className="flex items-center bg-gray-100 dark:bg-gray-700 rounded-lg p-1">
            <button
              type="button"
              onClick={() => setViewMode('kanban')}
              className={`px-2 sm:px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'kanban'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
              }`}
              aria-label="Kanban view"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2"
                />
              </svg>
            </button>
            <button
              type="button"
              onClick={() => setViewMode('list')}
              className={`px-2 sm:px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'list'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
              }`}
              aria-label="List view"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
              </svg>
            </button>
          </div>

          <Button leftIcon={<PlusIcon className="h-5 w-5" />} onClick={() => setShowForm(true)}>
            <span className="hidden sm:inline">Add Opportunity</span>
            <span className="sm:hidden">Add</span>
          </Button>
        </div>
      </div>

      {/* Pipeline Summary */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 sm:p-6 border border-transparent dark:border-gray-700">
        <div className="grid grid-cols-1 gap-4 sm:gap-6 sm:grid-cols-3">
          <div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Pipeline Value</p>
            <p
              className="mt-1 sm:mt-2 text-2xl sm:text-3xl font-semibold text-gray-900 dark:text-gray-100"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {formatCurrency(totalPipelineValue, 'USD')}
            </p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Open Deals</p>
            <p className="mt-1 sm:mt-2 text-2xl sm:text-3xl font-semibold text-gray-900 dark:text-gray-100">
              {openDeals}
            </p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Active Leads</p>
            <p className="mt-1 sm:mt-2 text-2xl sm:text-3xl font-semibold text-gray-900 dark:text-gray-100">
              {totalLeadsInPipeline}
            </p>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
          <p className="text-sm font-medium text-red-800 dark:text-red-300">
            {error instanceof Error ? error.message : 'Failed to load pipeline data'}
          </p>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <Spinner size="lg" />
        </div>
      ) : viewMode === 'kanban' ? (
        !hasKanbanData ? (
          <div className="text-center py-12">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No pipeline stages configured. Create pipeline stages in settings.
            </p>
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <label htmlFor="pipeline-search" className="sr-only">
                Search pipeline
              </label>
              <div className="relative w-full sm:max-w-sm">
                <svg
                  className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-gray-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="m21 21-4.3-4.3M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z"
                  />
                </svg>
                <input
                  id="pipeline-search"
                  type="search"
                  inputMode="search"
                  autoComplete="off"
                  spellCheck={false}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search leads + deals by name, company, email..."
                  className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 pl-9 pr-9 py-1.5 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => setSearchQuery('')}
                    aria-label="Clear search"
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                )}
              </div>
              {isFiltering && (
                <p
                  className="text-xs text-gray-500 dark:text-gray-400"
                  aria-live="polite"
                  role="status"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  {filteredCount} of {totalCount} match
                </p>
              )}
            </div>
            <DndContext
              sensors={sensors}
              collisionDetection={collisionDetection}
              onDragStart={handleDragStart}
              onDragEnd={handleDragEnd}
            >
              <div className="overflow-x-auto pb-4">
              <div className="flex flex-col md:flex-row gap-3 md:min-w-max items-start">
                {leadStages.length > 0 && (
                  <>
                    <div className="flex flex-col md:flex-row gap-3">
                      {leadStages.map((stage) => (
                        <LeadStageColumn
                          key={`lead-${stage.stage_id}`}
                          stage={stage}
                          isDragging={isDraggingLead}
                        />
                      ))}
                    </div>

                    {oppStages.length > 0 && (
                      <div className="flex flex-col items-center justify-start pt-8 px-1 shrink-0">
                        <div className="w-px h-16 bg-gray-300 dark:bg-gray-600" />
                        <div className="my-2 px-2 py-1 rounded-full bg-gray-200 dark:bg-gray-700 text-xs font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap">
                          Conversion
                        </div>
                        <svg
                          className="w-4 h-4 text-gray-400 dark:text-gray-500"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          aria-hidden="true"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M13 7l5 5m0 0l-5 5m5-5H6"
                          />
                        </svg>
                        <div className="w-px h-16 bg-gray-300 dark:bg-gray-600" />
                      </div>
                    )}
                  </>
                )}

                {oppStages.length > 0 && (
                  <div className="flex flex-col md:flex-row gap-3">
                    {oppStages.map((stage) => (
                      <OpportunityStageColumn
                        key={`opp-${stage.stage_id}`}
                        stage={stage}
                        isDragging={isDraggingOpp}
                      />
                    ))}
                  </div>
                )}
              </div>

              <div className="flex items-center gap-6 mt-4 pt-3 border-t border-gray-200 dark:border-gray-700">
                {leadStages.length > 0 && (
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded bg-blue-100 dark:bg-blue-900/40 border border-blue-300 dark:border-blue-700" />
                    <span className="text-xs text-gray-500 dark:text-gray-400">Leads</span>
                  </div>
                )}
                {oppStages.length > 0 && (
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded bg-emerald-100 dark:bg-emerald-900/40 border border-emerald-300 dark:border-emerald-700" />
                    <span className="text-xs text-gray-500 dark:text-gray-400">Opportunities</span>
                  </div>
                )}
              </div>
            </div>

              <DragOverlay>
                {activeLead ? <LeadDragOverlay lead={activeLead} /> : null}
                {activeOpp ? <OppDragOverlay opp={activeOpp} /> : null}
              </DragOverlay>
            </DndContext>
          </>
        )
      ) : (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
          {opportunityItems.length === 0 ? (
            <div className="text-center py-12 px-4">
              <svg
                className="mx-auto h-12 w-12 text-gray-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No opportunities</h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Get started by creating a new opportunity.
              </p>
              <div className="mt-6">
                <Button onClick={() => setShowForm(true)}>Add Opportunity</Button>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-900">
                  <tr>
                    <th
                      scope="col"
                      className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Opportunity
                    </th>
                    <th
                      scope="col"
                      className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Value
                    </th>
                    <th
                      scope="col"
                      className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Stage
                    </th>
                    <th
                      scope="col"
                      className="hidden sm:table-cell px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Probability
                    </th>
                    <th
                      scope="col"
                      className="hidden md:table-cell px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Close Date
                    </th>
                    <th scope="col" className="relative px-4 sm:px-6 py-3">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {opportunityItems.map((opp) => {
                    const stageName =
                      opp.pipeline_stage?.name?.toLowerCase().replace(/\s+/g, '_') ?? '';
                    return (
                      <tr
                        key={opp.id}
                        role="button"
                        tabIndex={0}
                        className="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
                        onClick={(e) => {
                          if ((e.target as HTMLElement).closest('a, button')) return;
                          if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
                          if (window.getSelection()?.toString()) return;
                          navigate(`/opportunities/${opp.id}`);
                        }}
                        onKeyDown={(e) => {
                          if (e.target !== e.currentTarget) return;
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            navigate(`/opportunities/${opp.id}`);
                          }
                        }}
                      >
                        <td className="px-4 sm:px-6 py-4">
                          <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate max-w-[150px] sm:max-w-none">
                            <EntityLink type="opportunity" id={opp.id}>
                              {opp.name}
                            </EntityLink>
                          </div>
                          {opp.company?.name && (
                            <div className="text-sm text-gray-500 dark:text-gray-400 truncate max-w-[150px] sm:max-w-none">
                              <EntityLink type="company" id={opp.company.id} variant="muted">
                                {opp.company.name}
                              </EntityLink>
                            </div>
                          )}
                        </td>
                        <td
                          className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-gray-100"
                          style={{ fontVariantNumeric: 'tabular-nums' }}
                        >
                          {formatCurrency(opp.amount ?? 0, opp.currency ?? 'USD')}
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          <span className={getStatusBadgeClasses(stageName, 'opportunity')}>
                            {opp.pipeline_stage?.name ?? stageName}
                          </span>
                        </td>
                        <td className="hidden sm:table-cell px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          {formatPercentage(opp.probability ?? 0)}
                        </td>
                        <td className="hidden md:table-cell px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          {formatDate(opp.expected_close_date)}
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditingOpportunity(opp);
                              setShowForm(true);
                            }}
                            className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300"
                          >
                            Edit
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Form Modal */}
      <Modal
        isOpen={showForm}
        onClose={handleFormCancel}
        title={editingOpportunity ? 'Edit Opportunity' : 'Add Opportunity'}
        size="full"
        fullScreenOnMobile
      >
        <div className="space-y-6">
          <OpportunityForm
            initialData={getInitialFormData()}
            onSubmit={handleFormSubmit}
            onCancel={handleFormCancel}
            isLoading={createOpportunityMutation.isPending || updateOpportunityMutation.isPending}
            submitLabel={editingOpportunity ? 'Update Opportunity' : 'Create Opportunity'}
            contacts={contactsList}
            companies={companiesList}
          />
        </div>
      </Modal>
    </div>
  );
}

export default PipelinePage;

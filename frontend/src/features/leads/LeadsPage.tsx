import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { PlusIcon, ViewColumnsIcon } from '@heroicons/react/24/outline';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Modal, ConfirmDialog, PaginationBar } from '../../components/ui';
import { SkeletonTable } from '../../components/ui/Skeleton';
import { DuplicateWarningModal } from '../../components/shared/DuplicateWarningModal';
import { SortableTh } from '../../components/shared/SortableTh';
import { LeadForm, LeadFormData } from './components/LeadForm';
import { BulkActionToolbar, type BulkStageOption } from './components/BulkActionToolbar';
import { LeadEmailCampaignModal } from './components/LeadEmailCampaignModal';
import { AddToCampaignModal } from './components/AddToCampaignModal';
import {
  useLeads,
  useCreateLead,
  useUpdateLead,
  useDeleteLead,
  useLeadPipelineStages,
  leadKeys,
  leadPipelineKeys,
} from '../../hooks/useLeads';
import { leadsApi } from '../../api/leads';
import { useCheckDuplicates } from '../../hooks/useDedup';
import {
  useListPageDefaults,
  useListSortPersistence,
} from '../../hooks/useListPageDefaults';
import { useUsers } from '../../hooks/useAuth';
import { bulkUpdate, bulkAssign, bulkDelete } from '../../api/importExport';
import { getStatusBadgeClasses, formatStatusLabel, getScoreColor } from '../../utils';
import { formatDate } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
import { useAuthStore } from '../../store/authStore';
import type { Lead, LeadCreate, LeadUpdate, ApiError, PipelineStage } from '../../types';
import type { DuplicateMatch } from '../../api/dedup';
import clsx from 'clsx';

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'new', label: 'New' },
  { value: 'contacted', label: 'Contacted' },
  { value: 'qualified', label: 'Qualified' },
  { value: 'unqualified', label: 'Unqualified' },
  { value: 'converted', label: 'Converted' },
  { value: 'lost', label: 'Lost' },
];

// Scoring factors awarded by the backend — kept in sync with
// backend/src/leads/scoring.py::LeadScorer. Drives the hover hint that
// shows each component as "12 / 20" so users see both the awarded *and*
// maximum value. Declared as a tuple-array (not an object) so the
// rendering order is stable regardless of JSON key order.
const SCORE_FACTORS: ReadonlyArray<{ key: string; label: string; max: number }> = [
  { key: 'profile_completeness', label: 'Profile completeness', max: 20 },
  { key: 'company_info', label: 'Company info', max: 15 },
  { key: 'budget', label: 'Budget', max: 20 },
  { key: 'industry', label: 'Industry match', max: 15 },
  { key: 'source_quality', label: 'Source quality', max: 15 },
  { key: 'engagement', label: 'Engagement', max: 15 },
];

const SCORE_HEADER_HINT =
  'Lead score (0–100) is auto-calculated from profile completeness, company info, budget, industry match, and source quality. Hover a row score for the per-factor breakdown.';

function buildScoreBreakdown(rawFactors: string | null | undefined): string {
  if (!rawFactors) return SCORE_HEADER_HINT;
  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(rawFactors) as Record<string, unknown>;
  } catch {
    return SCORE_HEADER_HINT;
  }
  const lines = SCORE_FACTORS.map(({ key, label, max }) => {
    const raw = parsed[key];
    const value = typeof raw === 'number' ? raw : 0;
    return `${label}: ${value} / ${max}`;
  });
  return `Lead score breakdown\n${lines.join('\n')}`;
}

function ScoreIndicator({
  score,
  factors,
}: {
  score: number;
  factors?: string | null;
}) {
  const percentage = Math.min(100, Math.max(0, score));
  const color = getScoreColor(score);
  const tooltip = buildScoreBreakdown(factors);

  return (
    <div
      className="flex items-center space-x-2"
      title={tooltip}
      aria-label={`Score ${score}. ${tooltip.replace(/\n/g, ' ')}`}
    >
      <div className="w-16 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div
          className={clsx('h-full rounded-full', {
            'bg-green-500': score >= 80,
            'bg-yellow-500': score >= 60 && score < 80,
            'bg-orange-500': score >= 40 && score < 60,
            'bg-red-500': score < 40,
          })}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className={clsx('text-sm font-medium', color)}>{score}</span>
    </div>
  );
}

const INITIAL_DELETE_CONFIRM = { isOpen: false, lead: null } as const;

interface StageSelectProps {
  lead: Lead;
  stageOptions: PipelineStage[];
  onChange: (lead: Lead, stageId: number | null) => void;
  disabled: boolean;
  variant: 'mobile' | 'desktop';
}

// File-local: shared <select> for inline stage edits on the leads list.
// Mobile and desktop variants differ only in id-prefix, padding, and
// whether the control stretches to fill its row.
function StageSelect({ lead, stageOptions, onChange, disabled, variant }: StageSelectProps) {
  const isMobile = variant === 'mobile';
  return (
    <select
      id={`${isMobile ? 'mobile-stage' : 'stage'}-${lead.id}`}
      value={lead.pipeline_stage_id ?? ''}
      onChange={(e) => {
        const v = e.target.value;
        onChange(lead, v === '' ? null : Number(v));
      }}
      disabled={disabled}
      className={clsx(
        'text-xs rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 px-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500',
        isMobile ? 'flex-1 min-w-0 py-1.5' : 'py-1',
      )}
      aria-label={`Move ${lead.full_name || 'lead'} to stage`}
    >
      <option value="">(unstaged)</option>
      {stageOptions.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
    </select>
  );
}

function LeadsPage() {
  usePageTitle('Leads');
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Bulk delete mirrors the backend's manager+ guard on
  // /import-export/bulk/delete — gate the UI so sales reps don't see a
  // red destructive button that would just 403 when they click it.
  const role = useAuthStore((s) => s.user?.role);
  const canBulkDelete = role === 'admin' || role === 'manager';

  const { savedPageSize, recordPageSize } = useListPageDefaults('leads');

  const searchQuery = searchParams.get('search') || '';
  const statusFilter = searchParams.get('status') || '';
  const currentPage = Number(searchParams.get('page') || '1');
  // URL wins; saved pref seeds when URL is bare. Both come from
  // user-controllable surfaces, so guard against NaN/0/negative — a
  // garbage `?per_page=abc` or a corrupted localStorage value would
  // otherwise ship `NaN` to the API and the user gets an empty list
  // with no error.
  const urlPerPage = Number(searchParams.get('per_page') || '');
  const candidatePageSize =
    Number.isFinite(urlPerPage) && urlPerPage > 0
      ? urlPerPage
      : (savedPageSize ?? 25);
  const pageSize =
    Number.isFinite(candidatePageSize) && candidatePageSize > 0
      ? candidatePageSize
      : 25;

  const debouncedSearch = useDebouncedValue(searchQuery, 300);
  const { sortBy, sortDir, toggle: toggleSort } = useListSortPersistence('leads');

  // Seed `per_page` URL from saved pref on first mount when URL is bare,
  // so back/forward + share-link stay correct after the saved size is
  // applied. We wait until `savedPageSize` is known (auth-store
  // rehydrating async would otherwise leave it `undefined` on first
  // render, the one-shot fires immediately, and the user's saved size
  // never seeds the URL on this navigation).
  const hasSeededPageSize = useRef(false);
  useEffect(() => {
    if (hasSeededPageSize.current) return;
    if (savedPageSize === undefined) return; // wait for prefs hydrate
    hasSeededPageSize.current = true;
    if (!searchParams.has('per_page') && savedPageSize !== 25) {
      setSearchParams(
        (prev) => {
          prev.set('per_page', String(savedPageSize));
          return prev;
        },
        { replace: true },
      );
    }
    // Re-evaluate when savedPageSize transitions from undefined → number.
    // After the ref locks, later prefs changes don't re-seed (URL wins
    // mid-session; the new saved size is honored on next mount).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedPageSize]);

  const setSearchQuery = (q: string) =>
    setSearchParams((prev) => { if (q) prev.set('search', q); else prev.delete('search'); prev.delete('page'); return prev; }, { replace: true });
  const setStatusFilter = (s: string) =>
    setSearchParams((prev) => { if (s) prev.set('status', s); else prev.delete('status'); prev.delete('page'); return prev; }, { replace: true });
  const setCurrentPage = (p: number) =>
    setSearchParams((prev) => { if (p === 1) prev.delete('page'); else prev.set('page', String(p)); return prev; }, { replace: true });
  const setPageSize = (n: number) => {
    recordPageSize(n);
    setSearchParams((prev) => { if (n === 25) prev.delete('per_page'); else prev.set('per_page', String(n)); prev.delete('page'); return prev; }, { replace: true });
  };

  const clearFilters = () => {
    setSearchParams((prev) => {
      prev.delete('search');
      prev.delete('status');
      prev.delete('page');
      return prev;
    }, { replace: true });
  };

  const [showForm, setShowForm] = useState(false);
  const [formDirty, setFormDirty] = useState(false);
  const [discardConfirmOpen, setDiscardConfirmOpen] = useState(false);
  const [editingLead, setEditingLead] = useState<Lead | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; lead: Lead | null }>(INITIAL_DELETE_CONFIRM);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [showCampaignModal, setShowCampaignModal] = useState(false);
  const [showAddToCampaign, setShowAddToCampaign] = useState(false);
  const [pendingFormData, setPendingFormData] = useState<LeadFormData | null>(null);
  const [duplicateResults, setDuplicateResults] = useState<DuplicateMatch[]>([]);
  const [showDuplicateWarning, setShowDuplicateWarning] = useState(false);

  // Use the hooks for data fetching
  const {
    data: leadsData,
    isLoading,
    error,
  } = useLeads({
    page: currentPage,
    page_size: pageSize,
    search: debouncedSearch || undefined,
    status: statusFilter || undefined,
    ...(sortBy && { order_by: sortBy, order_dir: sortDir }),
  });

  // Sorting changes ordering — drop back to page 1 so we don't land on an
  // offset that no longer corresponds to where the user expected to be.
  const handleSortToggle = (field: string) => {
    setSearchParams(
      (prev) => {
        prev.delete('page');
        return prev;
      },
      { replace: true },
    );
    toggleSort(field);
  };

  const createLeadMutation = useCreateLead();
  const updateLeadMutation = useUpdateLead();
  const deleteLeadMutation = useDeleteLead();
  const checkDuplicatesMutation = useCheckDuplicates();
  const { data: usersData } = useUsers(0, 100, { enabled: selectedIds.length > 0 });
  const { data: pipelineStagesData } = useLeadPipelineStages();
  const queryClient = useQueryClient();

  // Pipeline-stage map keyed by id for quick label lookup in the per-row
  // dropdown. Built off the active-only list returned by the hook —
  // Won/Lost are kept so legacy rows already in those stages render
  // their current value rather than "(unstaged)".
  const stageOptions = useMemo(() => {
    return ((pipelineStagesData ?? []) as PipelineStage[]).filter(
      (s) => s.is_active,
    );
  }, [pipelineStagesData]);

  // Stage targets surfaced in the bulk "Change Stage" menu. Includes an
  // "Off pipeline" sentinel so admins can clear the stage on selected
  // leads (mirrors the per-row dropdown's empty option).
  const bulkStageOptions = useMemo<BulkStageOption[]>(
    () => [
      ...stageOptions.map((s) => ({ id: s.id, label: s.name })),
      { id: null, label: 'Off pipeline' },
    ],
    [stageOptions],
  );

  const [bulkMoving, setBulkMoving] = useState(false);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);

  // Per-row stage edit. Fires a PATCH and invalidates list + kanban so
  // both views stay in sync. On 4xx, invalidate the list query so the
  // controlled <select> snaps back to the server's value — otherwise
  // the dropdown stays visually on the failed target and the toast is
  // the only signal anything broke.
  const handleRowStageChange = async (lead: Lead, newStageId: number | null) => {
    if ((lead.pipeline_stage_id ?? null) === newStageId) return;
    try {
      await updateLeadMutation.mutateAsync({
        id: lead.id,
        data: { pipeline_stage_id: newStageId },
      });
      queryClient.invalidateQueries({ queryKey: leadPipelineKeys.all });
      showSuccess(
        newStageId == null
          ? `${lead.full_name || 'Lead'} taken off the pipeline`
          : `${lead.full_name || 'Lead'} moved`,
      );
    } catch (err) {
      // Force the <select> back to the persisted value by refetching.
      queryClient.invalidateQueries({ queryKey: leadKeys.lists() });
      const detail = (err as ApiError | null)?.detail;
      showError(detail || 'Failed to update stage');
    }
  };

  const handleBulkMoveToStage = async (stageId: number | null) => {
    if (selectedIds.length === 0) return;
    setBulkMoving(true);
    try {
      // Fan out in chunks of ``BULK_MOVE_CONCURRENCY`` to avoid hammering
      // the backend with 25+ concurrent /move requests — production saw
      // 503s under load when the original fully-parallel version
      // exhausted the Neon connection pool mid-bulk. Each /move runs a
      // status sync + Won auto-convert, so the per-call DB cost is real.
      // /move requires a non-null stage id, so "Off pipeline" (null)
      // falls through to PATCH /leads/{id} with pipeline_stage_id: null
      // — PATCH was unified in PR #326 to status-sync + Won-convert
      // identically to /move.
      const BULK_MOVE_CONCURRENCY = 5;
      const results: PromiseSettledResult<unknown>[] = new Array(selectedIds.length);
      for (let i = 0; i < selectedIds.length; i += BULK_MOVE_CONCURRENCY) {
        const slice = selectedIds.slice(i, i + BULK_MOVE_CONCURRENCY);
        const sliceResults = await Promise.allSettled(
          slice.map((id) =>
            stageId == null
              ? leadsApi.update(id, { pipeline_stage_id: null })
              : leadsApi.moveLeadStage(id, { new_stage_id: stageId }),
          ),
        );
        sliceResults.forEach((r, j) => {
          results[i + j] = r;
        });
      }
      const failedIds = selectedIds.filter(
        (_id, i) => results[i]?.status === 'rejected',
      );
      const successes = results.length - failedIds.length;
      queryClient.invalidateQueries({ queryKey: leadKeys.all });
      queryClient.invalidateQueries({ queryKey: leadPipelineKeys.all });
      const targetLabel =
        stageId == null
          ? 'off the pipeline'
          : `to ${
              stageOptions.find((s) => s.id === stageId)?.name ?? 'the selected stage'
            }`;
      if (successes > 0) {
        showSuccess(
          `Moved ${successes} lead${successes === 1 ? '' : 's'} ${targetLabel}`,
        );
      }
      if (failedIds.length > 0) {
        // Surface a sample reason from the first rejection so admins
        // see WHY it broke (permission, 409 un-convert guard, etc.)
        // instead of a bare count. Keep the failed leads selected so
        // the user can retry just the broken ones without re-checking
        // every row.
        const firstReason = results.find((r) => r.status === 'rejected') as
          | PromiseRejectedResult
          | undefined;
        const sampleDetail = extractApiErrorDetail(firstReason?.reason);
        const sampleText = sampleDetail ? ` First error: ${sampleDetail}` : '';
        console.error('bulk move-to-stage had failures', {
          stageId,
          failedIds,
          reasons: results.filter((r) => r.status === 'rejected'),
        });
        showError(
          `${failedIds.length} lead${failedIds.length === 1 ? '' : 's'} failed to move.${sampleText}`,
        );
        setSelectedIds(failedIds);
      } else {
        setSelectedIds([]);
      }
    } finally {
      setBulkMoving(false);
    }
  };

  const bulkUpdateMutation = useMutation({
    mutationFn: (updates: Record<string, unknown>) =>
      bulkUpdate({ entity_type: 'leads', entity_ids: selectedIds, updates }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leadKeys.all });
      const count = selectedIds.length;
      setSelectedIds([]);
      showSuccess(`Updated ${count} lead${count === 1 ? '' : 's'}`);
    },
    onError: (err) => {
      showError(extractApiErrorDetail(err) || 'Failed to update leads');
    },
  });

  const bulkAssignMutation = useMutation({
    mutationFn: (ownerId: number) =>
      bulkAssign({ entity_type: 'leads', entity_ids: selectedIds, owner_id: ownerId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leadKeys.all });
      const count = selectedIds.length;
      setSelectedIds([]);
      showSuccess(`Reassigned ${count} lead${count === 1 ? '' : 's'}`);
    },
    onError: (err) => {
      showError(extractApiErrorDetail(err) || 'Failed to reassign leads');
    },
  });

  const bulkDeleteMutation = useMutation({
    mutationFn: () =>
      bulkDelete({ entity_type: 'leads', entity_ids: selectedIds }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: leadKeys.all });
      queryClient.invalidateQueries({ queryKey: leadPipelineKeys.all });
      setBulkDeleteOpen(false);
      if (result.success_count > 0) {
        showSuccess(
          `Deleted ${result.success_count} lead${result.success_count === 1 ? '' : 's'}`,
        );
      }
      if (result.error_count > 0) {
        // Surface the first server-reported reason so the user sees *why*
        // (e.g., "Has 3 contacts — reassign first") rather than a bare
        // count. Backend returns {id, error}; format both for clarity.
        const first = result.errors[0];
        const firstText = first ? `: #${first.id} ${first.error}` : '';
        showError(
          `${result.error_count} lead${result.error_count === 1 ? '' : 's'} failed to delete${firstText}`,
        );
        // Clear selection only when everything succeeded — otherwise
        // leave the survivors so the user can retry/inspect.
      } else if (result.success_count === 0) {
        // Defensive: server reported 0/0 (shouldn't happen because empty
        // entity_ids routes through raise_bad_request → onError, but
        // covers schema drift). Acknowledge so the user isn't left
        // staring at a silent dialog close.
        showError('No leads were deleted');
      } else {
        setSelectedIds([]);
      }
    },
    onError: (err) => {
      showError(extractApiErrorDetail(err) || 'Failed to delete leads');
    },
  });

  const leads = leadsData?.items ?? [];
  const totalPages = leadsData?.pages ?? 1;
  const total = leadsData?.total ?? 0;
  const hasActiveFilters = Boolean(searchQuery || statusFilter);

  const handleDeleteClick = (lead: Lead) => {
    setDeleteConfirm({ isOpen: true, lead });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm.lead) return;
    try {
      await deleteLeadMutation.mutateAsync(deleteConfirm.lead.id);
      setDeleteConfirm(INITIAL_DELETE_CONFIRM);
      showSuccess('Lead deleted successfully');
    } catch (err) {
      showError('Failed to delete lead');
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm(INITIAL_DELETE_CONFIRM);
  };

  const handleEdit = (lead: Lead) => {
    setFormDirty(false);
    setEditingLead(lead);
    setShowForm(true);
  };

  const doCreateLead = async (data: LeadFormData) => {
    // On create, empty optional fields are sent as undefined so Pydantic
    // applies its defaults / leaves them NULL rather than rejecting an
    // empty `EmailStr`.
    const createData: LeadCreate = {
      first_name: data.firstName?.trim() || undefined,
      last_name: data.lastName?.trim() || undefined,
      email: data.email?.trim() || undefined,
      phone: data.phone?.trim() || undefined,
      company_name: data.company?.trim() || undefined,
      job_title: data.jobTitle?.trim() || undefined,
      status: data.status,
      source_id: data.source_id ?? undefined,
      pipeline_stage_id: data.pipeline_stage_id ?? undefined,
      sales_code: data.salesCode?.trim() || undefined,
      description: data.notes?.trim() || undefined,
      budget_currency: 'USD',
    };
    await createLeadMutation.mutateAsync(createData);
    showSuccess('Lead created successfully');
    setShowForm(false);
    setEditingLead(null);
    setPendingFormData(null);
    setFormDirty(false);
  };

  const handleFormSubmit = async (data: LeadFormData) => {
    try {
      if (editingLead) {
        // On update, cleared optional fields are sent as null (not
        // undefined) so Pydantic sees them as `set`, and the service
        // applies the clear instead of silently keeping the old value.
        // EmailStr is the one exception: empty email is sent as null
        // since "" is not a valid EmailStr. Required string `first_name`
        // / `last_name` are passed through trim().
        const updateData: LeadUpdate = {
          first_name: data.firstName?.trim() || null,
          last_name: data.lastName?.trim() || null,
          email: data.email?.trim() || null,
          phone: data.phone?.trim() || null,
          company_name: data.company?.trim() || null,
          job_title: data.jobTitle?.trim() || null,
          source_id: data.source_id ?? null,
          pipeline_stage_id: data.pipeline_stage_id ?? null,
          sales_code: data.salesCode?.trim() || null,
          description: data.notes?.trim() || null,
        };
        // Only send status when it changed. Re-asserting an existing
        // 'converted' status (e.g. on an orphan-converted row) trips the
        // server-side guard and 400s every unrelated edit.
        if (data.status && data.status !== editingLead.status) {
          updateData.status = data.status;
        }
        await updateLeadMutation.mutateAsync({
          id: editingLead.id,
          data: updateData,
        });
        showSuccess('Lead updated successfully');
        setShowForm(false);
        setEditingLead(null);
        setFormDirty(false);
      } else {
        // Check for duplicates before creating
        const result = await checkDuplicatesMutation.mutateAsync({
          entityType: 'leads',
          data: {
            ...(data.email ? { email: data.email } : {}),
            ...(data.phone ? { phone: data.phone } : {}),
          },
        });
        if (result.has_duplicates) {
          setPendingFormData(data);
          setDuplicateResults(result.duplicates);
          setShowDuplicateWarning(true);
          return;
        }
        await doCreateLead(data);
      }
    } catch (err) {
      const detail = (err as ApiError | null)?.detail;
      showError(detail || 'Failed to save lead');
    }
  };

  const handleCreateAnyway = async () => {
    if (!pendingFormData) return;
    setShowDuplicateWarning(false);
    try {
      await doCreateLead(pendingFormData);
    } catch {
      showError('Failed to create lead');
    }
  };

  const handleViewDuplicate = (id: number) => {
    setShowDuplicateWarning(false);
    setShowForm(false);
    setPendingFormData(null);
    navigate(`/leads/${id}`);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingLead(null);
    setFormDirty(false);
    setDiscardConfirmOpen(false);
  };

  const handleFormCancel = () => {
    if (formDirty) {
      setDiscardConfirmOpen(true);
      return;
    }
    closeForm();
  };

  const toggleSelectAll = () => {
    if (selectedIds.length === leads.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(leads.map((l) => l.id));
    }
  };

  const toggleSelectOne = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  const getInitialFormData = (): Partial<LeadFormData> | undefined => {
    if (!editingLead) return undefined;
    return {
      firstName: editingLead.first_name || '',
      lastName: editingLead.last_name || '',
      email: editingLead.email || '',
      phone: editingLead.phone || '',
      company: editingLead.company_name || '',
      jobTitle: editingLead.job_title || '',
      source_id: editingLead.source?.id ?? null,
      pipeline_stage_id: editingLead.pipeline_stage_id ?? null,
      status: editingLead.status,
      salesCode: editingLead.sales_code || '',
      notes: editingLead.description || '',
    };
  };

  return (
    <div className="space-y-6" data-guide="leads-page">
      {/* Header */}
      <div
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
        data-guide="leads-header"
      >
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Leads</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Track and manage your sales leads
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to="/pipeline"
            data-guide="leads-pipeline-link"
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-500"
            aria-label="Open the pipeline kanban board"
          >
            <ViewColumnsIcon className="h-4 w-4" aria-hidden="true" />
            <span className="hidden sm:inline">Pipeline</span>
          </Link>

          {selectedIds.length > 0 && (
            <>
              <Button
                variant="secondary"
                onClick={() => setShowAddToCampaign(true)}
                aria-label={`Add ${selectedIds.length} leads to campaign`}
              >
                Add to Campaign ({selectedIds.length})
              </Button>
              <Button
                variant="secondary"
                onClick={() => setShowCampaignModal(true)}
              >
                Send Email ({selectedIds.length})
              </Button>
            </>
          )}

          <Button
            leftIcon={<PlusIcon className="h-5 w-5" />}
            onClick={() => {
              setFormDirty(false);
              setShowForm(true);
            }}
            className="w-full sm:w-auto"
          >
            Add Lead
          </Button>
        </div>
      </div>

      {/* Search and Filters */}
      <div
        className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 border border-transparent dark:border-gray-700"
        data-guide="leads-filters"
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:gap-4">
          <div className="flex-1">
            <label htmlFor="search" className="sr-only">
              Search leads
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <svg
                  className="h-5 w-5 text-gray-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
              </div>
              <input
                type="search"
                name="search"
                id="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="block w-full pl-10 pr-3 py-2.5 sm:py-2 border border-gray-300 dark:border-gray-600 rounded-md leading-5 bg-white dark:bg-gray-700 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus-visible:outline-none focus-visible:placeholder-gray-400 focus-visible:ring-1 focus-visible:ring-primary-500 focus-visible:border-primary-500 text-base sm:text-sm"
                placeholder="Search by name, email, or company..."
              />
            </div>
          </div>
          <div className="flex gap-3 sm:gap-4">
            <div className="flex-1 sm:flex-none sm:w-48">
              <label htmlFor="status-filter" className="sr-only">Filter by status</label>
              <select
                id="status-filter"
                name="status"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 py-2.5 sm:py-2 text-base sm:text-sm"
              >
                {statusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
          <div className="flex">
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800 dark:text-red-300">
                {error instanceof Error ? error.message : 'An error occurred'}
              </h3>
            </div>
          </div>
        </div>
      )}

      {/* Delete Error Message */}
      {deleteLeadMutation.isError && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
          <div className="flex">
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800 dark:text-red-300">
                Failed to delete lead
              </h3>
            </div>
          </div>
        </div>
      )}

      {/* Leads Table */}
      <div
        className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700"
        data-guide="leads-table"
      >
        {isLoading ? (
          <SkeletonTable rows={5} cols={7} />
        ) : leads.length === 0 ? (
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
                d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
              />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No leads</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {hasActiveFilters
                ? 'No leads match the current search or filters.'
                : 'Get started by creating a new lead.'}
            </p>
            <div className="mt-6">
              {hasActiveFilters ? (
                <Button variant="secondary" onClick={clearFilters} className="w-full sm:w-auto">
                  Clear filters
                </Button>
              ) : (
                <Button onClick={() => { setFormDirty(false); setShowForm(true); }} className="w-full sm:w-auto">Add Lead</Button>
              )}
            </div>
          </div>
        ) : (
          <>
            {/* Mobile Card View */}
            <div className="block md:hidden divide-y divide-gray-200 dark:divide-gray-700">
              {leads.map((lead: Lead) => (
                <div key={lead.id} className={clsx('p-4 space-y-3', selectedIds.includes(lead.id) && 'bg-primary-50 dark:bg-primary-900/20')}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start gap-3 min-w-0 flex-1">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(lead.id)}
                        onChange={() => toggleSelectOne(lead.id)}
                        aria-label={`Select ${lead.full_name || 'lead'}`}
                        className="mt-1 rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                      />
                      <div className="min-w-0 flex-1">
                        <Link
                          to={`/leads/${lead.id}`}
                          className="text-sm font-medium text-primary-600 hover:text-primary-900 dark:hover:text-primary-300 block truncate"
                        >
                          {lead.full_name || 'Unnamed Lead'}
                        </Link>
                        <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{lead.email || '-'}</p>
                        {lead.company_name && (
                          <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{lead.company_name}</p>
                        )}
                        {lead.phone && (
                          <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{lead.phone}</p>
                        )}
                      </div>
                    </div>
                    <span className={clsx(getStatusBadgeClasses(lead.status, 'lead'), 'flex-shrink-0')}>
                      {formatStatusLabel(lead.status)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <ScoreIndicator score={lead.score} factors={lead.score_factors} />
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {lead.source?.name ? formatStatusLabel(lead.source.name) : '-'}
                      </span>
                    </div>
                    <span className="text-xs text-gray-400 dark:text-gray-500">{formatDate(lead.created_at)}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <label
                      htmlFor={`mobile-stage-${lead.id}`}
                      className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap"
                    >
                      Stage
                    </label>
                    <StageSelect
                      lead={lead}
                      stageOptions={stageOptions}
                      onChange={handleRowStageChange}
                      disabled={updateLeadMutation.isPending}
                      variant="mobile"
                    />
                  </div>
                  <div className="flex gap-4 pt-2 border-t border-gray-100 dark:border-gray-700">
                    <button
                      onClick={() => handleEdit(lead)}
                      className="flex-1 text-center py-2 text-sm font-medium text-primary-600 hover:text-primary-900 dark:hover:text-primary-300 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDeleteClick(lead)}
                      className="flex-1 text-center py-2 text-sm font-medium text-red-600 hover:text-red-900 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                      disabled={deleteLeadMutation.isPending}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Desktop Table View */}
            <div className="hidden md:block overflow-x-auto">
              <table data-list-table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="sticky top-0 z-10 bg-gray-50 dark:bg-gray-900">
                  <tr>
                    <th scope="col" className="px-4 py-3 w-10">
                      <input
                        type="checkbox"
                        checked={leads.length > 0 && selectedIds.length === leads.length}
                        onChange={toggleSelectAll}
                        aria-label="Select all leads"
                        className="rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                      />
                    </th>
                    <SortableTh field="name" label="Name" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} />
                    <SortableTh field="company" label="Company" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} />
                    <SortableTh field="status" label="Status" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} />
                    <SortableTh field="stage" label="Stage" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} />
                    <SortableTh field="score" label="Score" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} helpText={SCORE_HEADER_HINT} />
                    <SortableTh field="source" label="Source" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} />
                    <SortableTh field="created_at" label="Created" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} />
                    <th scope="col" className="relative px-6 py-3">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {leads.map((lead: Lead) => (
                    <tr key={lead.id} className={clsx('hover:bg-gray-50 dark:hover:bg-gray-700', selectedIds.includes(lead.id) && 'bg-primary-50 dark:bg-primary-900/20')}>
                      <td className="px-4 py-4 w-10">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(lead.id)}
                          onChange={() => toggleSelectOne(lead.id)}
                          aria-label={`Select ${lead.full_name || 'lead'}`}
                          className="rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                        />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <Link
                          to={`/leads/${lead.id}`}
                          className="text-sm font-medium text-primary-600 hover:text-primary-900"
                        >
                          {lead.full_name || 'Unnamed Lead'}
                        </Link>
                        <p className="text-sm text-gray-500 dark:text-gray-400">{lead.email || '-'}</p>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {lead.company_name || '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={getStatusBadgeClasses(lead.status, 'lead')}>
                          {formatStatusLabel(lead.status)}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <label htmlFor={`stage-${lead.id}`} className="sr-only">
                          Pipeline stage for {lead.full_name || 'lead'}
                        </label>
                        <StageSelect
                          lead={lead}
                          stageOptions={stageOptions}
                          onChange={handleRowStageChange}
                          disabled={updateLeadMutation.isPending}
                          variant="desktop"
                        />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <ScoreIndicator score={lead.score} factors={lead.score_factors} />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {lead.source?.name ? formatStatusLabel(lead.source.name) : '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(lead.created_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <button
                          onClick={() => handleEdit(lead)}
                          className="text-primary-600 hover:text-primary-900 dark:hover:text-primary-300 mr-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded"
                          aria-label={`Edit ${lead.full_name || 'lead'}`}
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDeleteClick(lead)}
                          className="text-red-600 hover:text-red-900 dark:hover:text-red-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 rounded"
                          disabled={deleteLeadMutation.isPending}
                          aria-label={`Delete ${lead.full_name || 'lead'}`}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="bg-white dark:bg-gray-800 px-4 py-3 border-t border-gray-200 dark:border-gray-700 sm:px-6">
              <div className="flex items-center gap-4 mb-2 md:mb-0">
                <select
                  value={pageSize}
                  onChange={(e) => setPageSize(Number(e.target.value))}
                  aria-label="Results per page"
                  className="text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 px-2 py-1"
                >
                  <option value={10}>10 / page</option>
                  <option value={25}>25 / page</option>
                  <option value={50}>50 / page</option>
                  <option value={100}>100 / page</option>
                </select>
              </div>
              <PaginationBar
                page={currentPage}
                pages={totalPages}
                total={total}
                pageSize={pageSize}
                onPageChange={setCurrentPage}
              />
            </div>
          </>
        )}
      </div>

      {/* Bulk Action Toolbar */}
      <BulkActionToolbar
        selectedIds={selectedIds}
        entityType="lead(s)"
        onBulkUpdate={async (updates) => { await bulkUpdateMutation.mutateAsync(updates); }}
        onBulkAssign={async (ownerId) => { await bulkAssignMutation.mutateAsync(ownerId); }}
        onBulkMoveStage={handleBulkMoveToStage}
        onBulkDelete={canBulkDelete ? () => setBulkDeleteOpen(true) : undefined}
        onClearSelection={() => setSelectedIds([])}
        isLoading={
          bulkUpdateMutation.isPending ||
          bulkAssignMutation.isPending ||
          bulkDeleteMutation.isPending ||
          bulkMoving
        }
        users={(usersData ?? []).map((u: { id: number; full_name: string }) => ({ id: u.id, full_name: u.full_name }))}
        statusOptions={statusOptions.filter((o) => o.value !== '')}
        stageOptions={bulkStageOptions}
      />

      {/* Form Modal */}
      <Modal
        isOpen={showForm}
        onClose={closeForm}
        title={editingLead ? 'Edit Lead' : 'Add Lead'}
        size="lg"
        fullScreenOnMobile
        confirmClose={formDirty}
      >
        <LeadForm
          // Force a fresh form instance whenever the modal flips between
          // create / edit-A / edit-B. Without the key, RHF defaultValues
          // and the LeadForm internal source/pipeline state seed only on
          // mount, so swapping `editingLead` while the modal is still
          // visible would leak the prior lead's values onto the new PUT.
          key={editingLead?.id ?? 'new'}
          initialData={getInitialFormData()}
          onSubmit={handleFormSubmit}
          onCancel={handleFormCancel}
          isLoading={
            createLeadMutation.isPending || updateLeadMutation.isPending || checkDuplicatesMutation.isPending
          }
          submitLabel={editingLead ? 'Update Lead' : 'Create Lead'}
          score={editingLead?.score ?? null}
          requireContactFirst={!editingLead}
          onDirtyChange={setFormDirty}
        />
      </Modal>

      <ConfirmDialog
        isOpen={discardConfirmOpen}
        onClose={() => setDiscardConfirmOpen(false)}
        onConfirm={closeForm}
        title="Discard unsaved changes?"
        message="Your lead changes have not been saved."
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        variant="warning"
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete Lead"
        message={`Are you sure you want to delete ${deleteConfirm.lead?.full_name || 'this lead'}? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteLeadMutation.isPending}
      />

      {/* Bulk Delete Confirmation */}
      <ConfirmDialog
        isOpen={bulkDeleteOpen}
        onClose={() => setBulkDeleteOpen(false)}
        onConfirm={() => { bulkDeleteMutation.mutate(); }}
        title={`Delete ${selectedIds.length} lead${selectedIds.length === 1 ? '' : 's'}?`}
        message={`This will permanently delete ${selectedIds.length} lead${selectedIds.length === 1 ? '' : 's'} and all of their notes, activities, and emails. This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={bulkDeleteMutation.isPending}
      />

      {/* Email Campaign Modal */}
      <LeadEmailCampaignModal
        isOpen={showCampaignModal}
        onClose={() => setShowCampaignModal(false)}
        selectedLeadIds={selectedIds}
      />

      {/* Add to Campaign Modal */}
      <AddToCampaignModal
        isOpen={showAddToCampaign}
        onClose={() => setShowAddToCampaign(false)}
        selectedLeadIds={selectedIds}
        onSuccess={() => setSelectedIds([])}
      />

      {/* Duplicate Warning Modal */}
      <DuplicateWarningModal
        isOpen={showDuplicateWarning}
        onClose={() => { setShowDuplicateWarning(false); setPendingFormData(null); }}
        onCreateAnyway={handleCreateAnyway}
        onViewDuplicate={handleViewDuplicate}
        duplicates={duplicateResults}
        entityType="leads"
      />
    </div>
  );
}

export default LeadsPage;

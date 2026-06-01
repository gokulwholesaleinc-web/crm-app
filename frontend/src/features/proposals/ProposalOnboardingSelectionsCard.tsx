/**
 * Staff curation of a proposal's onboarding-template selections (Phase 3).
 *
 * The ordered list here drives Phase-3 auto-send: when the proposal is
 * accepted, its selected templates become the onboarding packet's documents
 * in this order. Staff can add active+PDF-backed templates, reorder them
 * (up/down — deliberately NOT a drag engine, per KISS), and remove them.
 *
 * Mirrors the self-contained card pattern used by ``ProposalAttachmentsCard``
 * in ``ProposalDetail.tsx``: own ``useQuery``/``useMutation`` against the
 * ``api/onboarding`` wrappers, toast on error via ``extractApiErrorDetail``.
 */

import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ChevronUpIcon,
  ChevronDownIcon,
  TrashIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';
import { Badge } from '../../components/ui';
import {
  listOnboardingTemplates,
  listProposalOnboardingSelections,
  setProposalOnboardingSelections,
  reorderProposalOnboardingSelections,
  removeProposalOnboardingSelection,
} from '../../api/onboarding';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
import type {
  OnboardingTemplate,
  OnboardingProposalSelection,
} from '../../types';

interface ProposalOnboardingSelectionsCardProps {
  proposalId: number;
  /** Once signed the packet has been (or is about to be) minted — lock edits. */
  isLocked: boolean;
}

export function ProposalOnboardingSelectionsCard({
  proposalId,
  isLocked,
}: ProposalOnboardingSelectionsCardProps) {
  const queryClient = useQueryClient();
  const selectionsKey = ['proposals', proposalId, 'onboarding-selections'] as const;

  const {
    data: selections,
    isLoading: selectionsLoading,
    error: selectionsError,
  } = useQuery({
    queryKey: selectionsKey,
    queryFn: () => listProposalOnboardingSelections(proposalId),
  });

  // Active, PDF-backed templates only — a retired/PDF-less one is a 422 on
  // set, so never offer it (matches the OnboardingSendPanel rule).
  const { data: templates, isLoading: templatesLoading } = useQuery({
    queryKey: ['onboarding-templates', 'selectable'],
    queryFn: () => listOnboardingTemplates(),
  });

  const selectableTemplates = useMemo<OnboardingTemplate[]>(
    () => (templates ?? []).filter((t) => t.is_active && t.has_pdf),
    [templates],
  );

  // Map for O(1) id→template lookup when rendering the ordered selection list.
  const templateById = useMemo(
    () => new Map((templates ?? []).map((t) => [t.id, t])),
    [templates],
  );

  const selectedTemplateIds = useMemo(
    () => new Set((selections ?? []).map((s) => s.template_id)),
    [selections],
  );

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: selectionsKey });

  // PUT replaces the whole ordered list, so add/remove-by-template both go
  // through here with the recomputed template_ids in display order.
  const setMutation = useMutation({
    mutationFn: (templateIds: number[]) =>
      setProposalOnboardingSelections(proposalId, templateIds),
    onSuccess: () => void invalidate(),
    onError: (err) =>
      showError(extractApiErrorDetail(err) ?? 'Failed to update onboarding documents'),
  });

  const reorderMutation = useMutation({
    mutationFn: (orderedIds: number[]) =>
      reorderProposalOnboardingSelections(proposalId, orderedIds),
    onSuccess: () => void invalidate(),
    onError: (err) =>
      showError(extractApiErrorDetail(err) ?? 'Failed to reorder onboarding documents'),
  });

  const removeMutation = useMutation({
    mutationFn: (selection: OnboardingProposalSelection) =>
      removeProposalOnboardingSelection(proposalId, selection.id),
    onSuccess: () => {
      void invalidate();
      showSuccess('Document removed from onboarding');
    },
    onError: (err) =>
      showError(extractApiErrorDetail(err) ?? 'Failed to remove onboarding document'),
  });

  const isBusy =
    setMutation.isPending || reorderMutation.isPending || removeMutation.isPending;
  const ordered = selections ?? [];

  const handleAdd = (templateId: number) => {
    if (isLocked) return;
    // Append the newly-picked template to the current order.
    const next = [...ordered.map((s) => s.template_id), templateId];
    setMutation.mutate(next);
  };

  const handleRemove = (selection: OnboardingProposalSelection) => {
    if (isLocked) return;
    removeMutation.mutate(selection);
  };

  const handleMove = (index: number, direction: -1 | 1) => {
    if (isLocked) return;
    const target = index + direction;
    if (target < 0 || target >= ordered.length) return;
    const orderedIds = ordered.map((s) => s.id);
    const moved = orderedIds[index];
    const displaced = orderedIds[target];
    if (moved === undefined || displaced === undefined) return;
    orderedIds[index] = displaced;
    orderedIds[target] = moved;
    reorderMutation.mutate(orderedIds);
  };

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-gray-100 dark:border-gray-700">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400">
          Onboarding documents
        </h2>
        {isLocked && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Locked — proposal signed
          </span>
        )}
      </div>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400 text-pretty">
        These templates are sent to the client when this proposal is accepted, in
        the order shown.
      </p>

      {selectionsError && !selectionsLoading && (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          Failed to load onboarding documents.
        </p>
      )}

      {selectionsLoading ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">Loading…</p>
      ) : ordered.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          No onboarding documents selected yet.
        </p>
      ) : (
        <ol className="divide-y divide-gray-200 dark:divide-gray-700 border border-gray-200 dark:border-gray-700 rounded">
          {ordered.map((selection, index) => {
            const template = templateById.get(selection.template_id);
            const name = template?.name ?? `Template #${selection.template_id}`;
            const isMissing = !template;
            return (
              <li
                key={selection.id}
                className="flex items-center justify-between gap-3 px-3 py-2"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span className="w-5 flex-shrink-0 text-xs text-gray-400 dark:text-gray-500 tabular-nums">
                    {index + 1}.
                  </span>
                  <span className="min-w-0 truncate text-sm font-medium text-gray-900 dark:text-gray-100">
                    {name}
                  </span>
                  {template?.requires_esign && (
                    <Badge variant="yellow" size="sm">
                      E-sign
                    </Badge>
                  )}
                  {isMissing && (
                    <Badge variant="red" size="sm">
                      Unavailable
                    </Badge>
                  )}
                </div>
                {!isLocked && (
                  <div className="flex flex-shrink-0 items-center gap-1">
                    <button
                      type="button"
                      aria-label={`Move ${name} up`}
                      onClick={() => handleMove(index, -1)}
                      disabled={index === 0 || isBusy}
                      className="p-1.5 text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 rounded disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-500"
                    >
                      <ChevronUpIcon className="h-4 w-4" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      aria-label={`Move ${name} down`}
                      onClick={() => handleMove(index, 1)}
                      disabled={index === ordered.length - 1 || isBusy}
                      className="p-1.5 text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 rounded disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-500"
                    >
                      <ChevronDownIcon className="h-4 w-4" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      aria-label={`Remove ${name} from onboarding`}
                      onClick={() => handleRemove(selection)}
                      disabled={isBusy}
                      className="p-1.5 text-gray-400 hover:text-red-600 dark:hover:text-red-400 rounded disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-500"
                    >
                      <TrashIcon className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}

      {!isLocked && (
        <div className="mt-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Add a document
          </h3>
          {templatesLoading ? (
            <p className="mt-2 text-sm text-gray-400 dark:text-gray-500">
              Loading templates…
            </p>
          ) : selectableTemplates.length === 0 ? (
            <p className="mt-2 text-sm text-gray-400 dark:text-gray-500">
              No active templates with an uploaded PDF are available.
            </p>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {selectableTemplates.map((t) => {
                const alreadySelected = selectedTemplateIds.has(t.id);
                return (
                  <li
                    key={t.id}
                    className="flex items-center justify-between gap-3 rounded border border-gray-200 dark:border-gray-700 px-3 py-2"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="min-w-0 truncate text-sm text-gray-900 dark:text-gray-100">
                        {t.name}
                      </span>
                      {t.requires_esign && (
                        <Badge variant="yellow" size="sm">
                          E-sign
                        </Badge>
                      )}
                    </div>
                    <button
                      type="button"
                      aria-label={
                        alreadySelected
                          ? `${t.name} is already added`
                          : `Add ${t.name} to onboarding`
                      }
                      onClick={() => handleAdd(t.id)}
                      disabled={alreadySelected || isBusy}
                      className="inline-flex flex-shrink-0 items-center gap-1 rounded px-2 py-1 text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-500"
                    >
                      <PlusIcon className="h-4 w-4" aria-hidden="true" />
                      {alreadySelected ? 'Added' : 'Add'}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default ProposalOnboardingSelectionsCard;

/**
 * "Saved packets" library section — the reusable onboarding bundles staff build
 * with the wizard. Lists each packet with its document count + a backend-driven
 * readiness badge ("Ready to send" / "Needs setup"), and offers build / retire /
 * restore / delete. Sending a packet happens from the "Send to client" panel
 * ("Start from a saved packet"); this section is curation only.
 */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  PlusIcon,
  ArchiveBoxXMarkIcon,
  ArrowUturnLeftIcon,
  TrashIcon,
  PencilSquareIcon,
  ClipboardDocumentListIcon,
} from '@heroicons/react/24/outline';
import { Button, Badge, Switch, ConfirmDialog } from '../../components/ui';
import { SkeletonTable } from '../../components/ui/Skeleton';
import { useAuthQuery } from '../../hooks/useAuthQuery';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
import {
  listOnboardingBundles,
  updateOnboardingBundle,
  deleteOnboardingBundle,
} from '../../api/onboarding';
import type { OnboardingBundleSummary } from '../../types';
import { OnboardingPacketWizard } from './OnboardingPacketWizard';
import { OnboardingPacketEditor } from './OnboardingPacketEditor';

const BUNDLES_KEY = ['onboarding-bundles'] as const;

export function SavedPacketsPanel() {
  const queryClient = useQueryClient();
  const [showWizard, setShowWizard] = useState(false);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [editTargetId, setEditTargetId] = useState<number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<OnboardingBundleSummary | null>(null);

  const {
    data: bundles = [],
    isLoading,
    error,
  } = useAuthQuery<OnboardingBundleSummary[]>({
    queryKey: [...BUNDLES_KEY, { includeInactive }],
    queryFn: () => listOnboardingBundles(includeInactive),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: BUNDLES_KEY });

  const retireMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) =>
      updateOnboardingBundle(id, { is_active: isActive }),
    onSuccess: () => void invalidate(),
    onError: (err) => showError(extractApiErrorDetail(err) ?? 'Failed to update packet'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteOnboardingBundle(id),
    onSuccess: () => {
      void invalidate();
      showSuccess('Saved packet deleted.');
      setDeleteTarget(null);
    },
    onError: (err) => showError(extractApiErrorDetail(err) ?? 'Failed to delete packet'),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-gray-500 dark:text-gray-400 text-pretty">
          Reusable, ordered sets of onboarding documents. Build one here, then
          send it to a client from “Send to client”.
        </p>
        <Button
          leftIcon={<PlusIcon className="h-5 w-5" aria-hidden="true" />}
          onClick={() => setShowWizard(true)}
          className="w-full sm:w-auto"
        >
          Build a packet
        </Button>
      </div>

      <Switch
        checked={includeInactive}
        onChange={setIncludeInactive}
        label="Show retired packets"
        size="sm"
      />

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          Failed to load saved packets.
        </p>
      )}

      {isLoading ? (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
          <SkeletonTable rows={3} cols={3} />
        </div>
      ) : bundles.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-transparent dark:border-gray-700 text-center py-12 px-4">
          <ClipboardDocumentListIcon className="mx-auto h-12 w-12 text-gray-400" aria-hidden="true" />
          <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">
            No saved packets yet
          </h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400 text-pretty">
            Build a packet once — a named, ordered set of documents — and reuse it
            for every new client.
          </p>
          <div className="mt-6 flex justify-center">
            <Button onClick={() => setShowWizard(true)}>Build a packet</Button>
          </div>
        </div>
      ) : (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700 divide-y divide-gray-200 dark:divide-gray-700">
          {bundles.map((bundle) => (
            <div
              key={bundle.id}
              className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                    {bundle.name}
                  </p>
                  {!bundle.is_active && <Badge variant="gray" size="sm">Retired</Badge>}
                  {bundle.send_ready ? (
                    <Badge variant="green" size="sm">Ready to send</Badge>
                  ) : (
                    <Badge variant="yellow" size="sm">Needs setup</Badge>
                  )}
                </div>
                {bundle.description && (
                  <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
                    {bundle.description}
                  </p>
                )}
                <p
                  className="mt-0.5 text-xs text-gray-400 dark:text-gray-500"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  {bundle.item_count} document{bundle.item_count === 1 ? '' : 's'}
                </p>
              </div>
              <div className="flex flex-shrink-0 flex-wrap gap-2">
                {bundle.is_active && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    leftIcon={<PencilSquareIcon className="h-4 w-4" aria-hidden="true" />}
                    onClick={() => setEditTargetId(bundle.id)}
                  >
                    Edit
                  </Button>
                )}
                {bundle.is_active ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    leftIcon={<ArchiveBoxXMarkIcon className="h-4 w-4" aria-hidden="true" />}
                    onClick={() =>
                      retireMutation.mutate({ id: bundle.id, isActive: false })
                    }
                  >
                    Retire
                  </Button>
                ) : (
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    leftIcon={<ArrowUturnLeftIcon className="h-4 w-4" aria-hidden="true" />}
                    onClick={() =>
                      retireMutation.mutate({ id: bundle.id, isActive: true })
                    }
                  >
                    Restore
                  </Button>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  leftIcon={<TrashIcon className="h-4 w-4" aria-hidden="true" />}
                  onClick={() => setDeleteTarget(bundle)}
                >
                  Delete
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <OnboardingPacketWizard isOpen={showWizard} onClose={() => setShowWizard(false)} />

      {editTargetId != null && (
        <OnboardingPacketEditor
          bundleId={editTargetId}
          onClose={() => setEditTargetId(null)}
        />
      )}

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
        title="Delete saved packet"
        message={`Delete “${deleteTarget?.name ?? ''}”? This removes the saved packet; the document templates it created stay in your library.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}

export default SavedPacketsPanel;

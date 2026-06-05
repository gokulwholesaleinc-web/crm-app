/**
 * Edit a saved packet's composition after creation: rename, reorder members,
 * remove a member, and add an existing template. Without this, staff with a
 * wrong-order / wrong-member / setup-required packet would have to delete and
 * rebuild. Reads the backend-computed send_ready per member so "needs setup"
 * documents are visible while editing.
 */

import { useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ChevronUpIcon,
  ChevronDownIcon,
  TrashIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';
import { Modal, ModalFooter, Button, Input, Select, Badge, Spinner } from '../../components/ui';
import { useAuthQuery } from '../../hooks/useAuthQuery';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
import {
  getOnboardingBundle,
  listOnboardingTemplates,
  updateOnboardingBundle,
  reorderOnboardingBundle,
  addOnboardingBundleItem,
  removeOnboardingBundleItem,
} from '../../api/onboarding';
import type {
  OnboardingBundleDetail,
  OnboardingBundleMember,
  OnboardingTemplate,
} from '../../types';

interface OnboardingPacketEditorProps {
  bundleId: number;
  onClose: () => void;
}

export function OnboardingPacketEditor({ bundleId, onClose }: OnboardingPacketEditorProps) {
  const detailKey = ['onboarding-bundle', bundleId] as const;
  const { data: detail, isLoading } = useAuthQuery<OnboardingBundleDetail>({
    queryKey: detailKey,
    queryFn: () => getOnboardingBundle(bundleId),
  });

  return (
    <Modal isOpen onClose={onClose} title="Edit saved packet" size="lg">
      {isLoading || !detail ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : (
        <EditorBody key={detail.id} detail={detail} detailKey={detailKey} onClose={onClose} />
      )}
    </Modal>
  );
}

function EditorBody({
  detail,
  detailKey,
  onClose,
}: {
  detail: OnboardingBundleDetail;
  detailKey: readonly ['onboarding-bundle', number];
  onClose: () => void;
}) {
  const bundleId = detail.id;
  const queryClient = useQueryClient();
  const [name, setName] = useState(detail.name);
  const [addTemplateId, setAddTemplateId] = useState<string>('');

  const { data: templates = [] } = useAuthQuery<OnboardingTemplate[]>({
    queryKey: ['onboarding-templates', 'packet-editor'],
    queryFn: () => listOnboardingTemplates(),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: detailKey });
    void queryClient.invalidateQueries({ queryKey: ['onboarding-bundles'] });
  };

  const onError = (fallback: string) => (err: unknown) =>
    showError(extractApiErrorDetail(err) ?? fallback);

  const renameMutation = useMutation({
    mutationFn: (newName: string) => updateOnboardingBundle(bundleId, { name: newName }),
    onSuccess: () => {
      invalidate();
      showSuccess('Packet renamed.');
    },
    onError: onError('Failed to rename packet'),
  });
  const reorderMutation = useMutation({
    mutationFn: (orderedItemIds: number[]) => reorderOnboardingBundle(bundleId, orderedItemIds),
    onSuccess: invalidate,
    onError: onError('Failed to reorder documents'),
  });
  const addMutation = useMutation({
    mutationFn: (templateId: number) => addOnboardingBundleItem(bundleId, templateId),
    onSuccess: () => {
      invalidate();
      setAddTemplateId('');
    },
    onError: onError('Failed to add document'),
  });
  const removeMutation = useMutation({
    mutationFn: (itemId: number) => removeOnboardingBundleItem(bundleId, itemId),
    onSuccess: invalidate,
    onError: onError('Failed to remove document'),
  });

  const isBusy =
    renameMutation.isPending ||
    reorderMutation.isPending ||
    addMutation.isPending ||
    removeMutation.isPending;

  const members = detail.members;
  const memberTemplateIds = useMemo(
    () => new Set(members.map((m) => m.template_id)),
    [members],
  );
  // Active templates not already in the packet, for the "add" picker.
  const addable = useMemo(
    () => templates.filter((t) => t.is_active && !memberTemplateIds.has(t.id)),
    [templates, memberTemplateIds],
  );

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= members.length) return;
    const orderedIds = members.map((m) => m.item_id);
    const a = orderedIds[index];
    const b = orderedIds[target];
    if (a === undefined || b === undefined) return;
    orderedIds[index] = b;
    orderedIds[target] = a;
    reorderMutation.mutate(orderedIds);
  };

  return (
    <div className="space-y-4">
      {/* Rename */}
      <div className="flex items-end gap-2">
        <Input
          label="Packet name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          name="packet-rename"
          className="flex-1"
        />
        <Button
          type="button"
          variant="secondary"
          disabled={isBusy || !name.trim() || name.trim() === detail.name}
          onClick={() => renameMutation.mutate(name.trim())}
        >
          Save name
        </Button>
      </div>

      {/* Members */}
      <div>
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Documents ({members.length})
        </h3>
        <ol className="mt-2 divide-y divide-gray-200 dark:divide-gray-700 rounded border border-gray-200 dark:border-gray-700">
          {members.map((m: OnboardingBundleMember, index) => (
            <li key={m.item_id} className="flex items-center gap-2 px-3 py-2">
              <span className="w-5 flex-shrink-0 text-xs text-gray-400 tabular-nums">
                {index + 1}.
              </span>
              <span className="min-w-0 flex-1 truncate text-sm text-gray-900 dark:text-gray-100">
                {m.name}
              </span>
              {!m.is_active && <Badge variant="gray" size="sm">Retired</Badge>}
              {m.send_ready ? (
                <Badge variant="green" size="sm">Ready</Badge>
              ) : (
                <Badge variant="yellow" size="sm">Needs setup</Badge>
              )}
              <div className="flex flex-shrink-0 items-center gap-1">
                <button
                  type="button"
                  aria-label={`Move ${m.name} up`}
                  onClick={() => move(index, -1)}
                  disabled={index === 0 || isBusy}
                  className="p-1.5 text-gray-400 hover:text-primary-600 rounded disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-500"
                >
                  <ChevronUpIcon className="h-4 w-4" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  aria-label={`Move ${m.name} down`}
                  onClick={() => move(index, 1)}
                  disabled={index === members.length - 1 || isBusy}
                  className="p-1.5 text-gray-400 hover:text-primary-600 rounded disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-500"
                >
                  <ChevronDownIcon className="h-4 w-4" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  aria-label={`Remove ${m.name}`}
                  onClick={() => removeMutation.mutate(m.item_id)}
                  disabled={isBusy || members.length <= 1}
                  title={members.length <= 1 ? 'A packet must keep at least one document' : undefined}
                  className="p-1.5 text-gray-400 hover:text-red-600 rounded disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-500"
                >
                  <TrashIcon className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </li>
          ))}
        </ol>
      </div>

      {/* Add an existing template */}
      <div className="flex items-end gap-2">
        <Select
          label="Add an existing template"
          value={addTemplateId}
          onChange={(e) => setAddTemplateId(e.target.value)}
          name="packet-add-template"
          options={[
            { value: '', label: addable.length ? 'Choose a template…' : 'No templates to add' },
            ...addable.map((t) => ({ value: String(t.id), label: t.name })),
          ]}
          className="flex-1"
          disabled={addable.length === 0}
        />
        <Button
          type="button"
          variant="secondary"
          leftIcon={<PlusIcon className="h-4 w-4" aria-hidden="true" />}
          disabled={isBusy || !addTemplateId}
          onClick={() => addTemplateId && addMutation.mutate(Number(addTemplateId))}
        >
          Add
        </Button>
      </div>

      <ModalFooter>
        <Button variant="secondary" onClick={onClose}>Done</Button>
      </ModalFooter>
    </div>
  );
}

export default OnboardingPacketEditor;

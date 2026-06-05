/**
 * "Build a packet" wizard — assemble a named, ordered set of onboarding
 * documents (a saved packet / bundle) once and reuse it across clients.
 *
 * Three steps: basics (name) → documents (ordered list) → review/create. Each
 * document mints a NEW template, sourced from a built-in starter, a clone of an
 * active questionnaire/upload template, or a blank spec. E-sign templates are
 * excluded from the clone picker (their PDF + placed fields are
 * template-specific — audit P0#4); a blank e-sign document can still be added
 * and is flagged "needs a PDF" (it isn't sendable until staff upload one — §4.7).
 */

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  PlusIcon,
  TrashIcon,
  ChevronUpIcon,
  ChevronDownIcon,
} from '@heroicons/react/24/outline';
import { Modal, ModalFooter, Button, Input, Select, Badge } from '../../components/ui';
import {
  listOnboardingStarters,
  listOnboardingTemplates,
  createOnboardingBundle,
} from '../../api/onboarding';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
import type {
  OnboardingBundleWizardItem,
  OnboardingDocumentKind,
  OnboardingStarter,
  OnboardingTemplate,
} from '../../types';

/** Max documents per packet — mirrors the backend ceiling (§10 Q4). */
const MAX_ITEMS = 20;

interface DraftItem {
  tempId: number;
  source: 'clone' | 'starter' | 'blank';
  name: string;
  kind: OnboardingDocumentKind;
  sourceTemplateId?: number;
  starterKey?: string;
}

interface OnboardingPacketWizardProps {
  isOpen: boolean;
  onClose: () => void;
  /** Called after a packet is created (the wizard already toasts + closes). */
  onCreated?: () => void;
}

type Step = 'basics' | 'documents' | 'review';

function kindBadge(kind: OnboardingDocumentKind) {
  if (kind === 'questionnaire') return <Badge variant="purple" size="sm">Questionnaire</Badge>;
  if (kind === 'upload_request') return <Badge variant="indigo" size="sm">Upload request</Badge>;
  return <Badge variant="yellow" size="sm">E-sign</Badge>;
}

export function OnboardingPacketWizard({
  isOpen,
  onClose,
  onCreated,
}: OnboardingPacketWizardProps) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>('basics');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [items, setItems] = useState<DraftItem[]>([]);
  const [nextId, setNextId] = useState(1);
  const [blankKind, setBlankKind] = useState<OnboardingDocumentKind>('questionnaire');

  const { data: starters = [] } = useQuery({
    queryKey: ['onboarding-starters'],
    queryFn: listOnboardingStarters,
    enabled: isOpen,
    staleTime: 5 * 60_000,
  });
  // Active templates for the clone picker — e-sign excluded (P0#4).
  const { data: templates = [] } = useQuery({
    queryKey: ['onboarding-templates', 'wizard-cloneable'],
    queryFn: () => listOnboardingTemplates(),
    enabled: isOpen,
  });
  const cloneable = useMemo<OnboardingTemplate[]>(
    () => templates.filter((t) => t.is_active && t.kind !== 'esign_pdf'),
    [templates],
  );

  const reset = () => {
    setStep('basics');
    setName('');
    setDescription('');
    setItems([]);
    setNextId(1);
    setBlankKind('questionnaire');
  };

  const close = () => {
    reset();
    onClose();
  };

  const createMutation = useMutation({
    mutationFn: createOnboardingBundle,
    onSuccess: (detail) => {
      queryClient.invalidateQueries({ queryKey: ['onboarding-bundles'] });
      // Minting clones/blanks created new templates — refresh that list too.
      queryClient.invalidateQueries({ queryKey: ['onboarding-templates'] });
      const notReady = detail.members.filter((m) => !m.send_ready).length;
      showSuccess(
        notReady > 0
          ? `Saved packet “${detail.name}” created. ${notReady} document${notReady === 1 ? '' : 's'} ${notReady === 1 ? 'needs' : 'need'} setup before this packet can be sent.`
          : `Saved packet “${detail.name}” created.`,
      );
      onCreated?.();
      close();
    },
    onError: (err) =>
      showError(extractApiErrorDetail(err) ?? 'Failed to create saved packet'),
  });

  const addItem = (item: Omit<DraftItem, 'tempId'>) => {
    if (items.length >= MAX_ITEMS) {
      showError(`A packet can hold at most ${MAX_ITEMS} documents.`);
      return;
    }
    setItems((curr) => [...curr, { ...item, tempId: nextId }]);
    setNextId((n) => n + 1);
  };

  const updateName = (tempId: number, value: string) =>
    setItems((curr) =>
      curr.map((it) => (it.tempId === tempId ? { ...it, name: value } : it)),
    );

  const removeItem = (tempId: number) =>
    setItems((curr) => curr.filter((it) => it.tempId !== tempId));

  const moveItem = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= items.length) return;
    setItems((curr) => {
      const next = [...curr];
      const moved = next[index];
      if (moved === undefined) return curr;
      next.splice(index, 1);
      next.splice(target, 0, moved);
      return next;
    });
  };

  const trimmedNames = items.map((it) => it.name.trim());
  const hasBlankName = trimmedNames.some((n) => n.length === 0);
  const hasDupName =
    new Set(trimmedNames).size !== trimmedNames.length;
  const canProceedBasics = name.trim().length > 0;
  const canCreate =
    canProceedBasics && items.length > 0 && !hasBlankName && !hasDupName;

  const handleCreate = () => {
    const payloadItems: OnboardingBundleWizardItem[] = items.map((it) => ({
      source: it.source,
      name: it.name.trim(),
      ...(it.source === 'clone' ? { source_template_id: it.sourceTemplateId } : {}),
      ...(it.source === 'starter' ? { starter_key: it.starterKey } : {}),
      ...(it.source === 'blank' ? { kind: it.kind } : {}),
    }));
    createMutation.mutate({
      name: name.trim(),
      description: description.trim() || null,
      items: payloadItems,
    });
  };

  return (
    <Modal isOpen={isOpen} onClose={close} title="Build a saved packet" size="lg">
      {/* Step indicator */}
      <ol className="mb-4 flex items-center gap-2 text-xs font-medium" aria-label="Wizard steps">
        {(['basics', 'documents', 'review'] as const).map((s, i) => (
          <li key={s} className="flex items-center gap-2">
            <span
              className={
                step === s
                  ? 'rounded-full bg-primary-600 px-2.5 py-1 text-white'
                  : 'rounded-full bg-gray-100 px-2.5 py-1 text-gray-500 dark:bg-gray-700 dark:text-gray-300'
              }
            >
              {i + 1}. {s === 'basics' ? 'Basics' : s === 'documents' ? 'Documents' : 'Review'}
            </span>
            {i < 2 && <span aria-hidden="true" className="text-gray-300">›</span>}
          </li>
        ))}
      </ol>

      {step === 'basics' && (
        <div className="space-y-4">
          <Input
            label="Packet name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            name="packet-name"
            placeholder="e.g. New client — full onboarding"
            autoComplete="off"
            required
          />
          <div>
            <label
              htmlFor="packet-description"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Description (optional)
            </label>
            <textarea
              id="packet-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus-visible:border-primary-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500"
              placeholder="What this packet is for…"
            />
          </div>
        </div>
      )}

      {step === 'documents' && (
        <div className="space-y-5">
          {/* The ordered draft list */}
          <div>
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Documents in this packet ({items.length})
            </h3>
            {items.length === 0 ? (
              <p className="mt-2 text-sm text-gray-400 dark:text-gray-500">
                No documents yet — add a starter, copy an existing template, or
                add a blank document below.
              </p>
            ) : (
              <ol className="mt-2 divide-y divide-gray-200 dark:divide-gray-700 rounded border border-gray-200 dark:border-gray-700">
                {items.map((it, index) => (
                  <li key={it.tempId} className="flex items-center gap-2 px-3 py-2">
                    <span className="w-5 flex-shrink-0 text-xs text-gray-400 tabular-nums">
                      {index + 1}.
                    </span>
                    <Input
                      aria-label={`Document ${index + 1} name`}
                      value={it.name}
                      onChange={(e) => updateName(it.tempId, e.target.value)}
                      name={`doc-name-${it.tempId}`}
                      className="min-w-0 flex-1"
                      error={it.name.trim() ? undefined : 'Required'}
                    />
                    {kindBadge(it.kind)}
                    <div className="flex flex-shrink-0 items-center gap-1">
                      <button
                        type="button"
                        aria-label={`Move document ${index + 1} up`}
                        onClick={() => moveItem(index, -1)}
                        disabled={index === 0}
                        className="p-1.5 text-gray-400 hover:text-primary-600 rounded disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-500"
                      >
                        <ChevronUpIcon className="h-4 w-4" aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Move document ${index + 1} down`}
                        onClick={() => moveItem(index, 1)}
                        disabled={index === items.length - 1}
                        className="p-1.5 text-gray-400 hover:text-primary-600 rounded disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-500"
                      >
                        <ChevronDownIcon className="h-4 w-4" aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Remove document ${index + 1}`}
                        onClick={() => removeItem(it.tempId)}
                        className="p-1.5 text-gray-400 hover:text-red-600 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-500"
                      >
                        <TrashIcon className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </div>
                  </li>
                ))}
              </ol>
            )}
            {hasDupName && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400" role="alert">
                Each document needs a unique name.
              </p>
            )}
          </div>

          {/* Add from a starter / existing template */}
          <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
              Add from a starter or template
            </h4>
            <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto pr-1">
              {starters.map((s: OnboardingStarter) => (
                <li
                  key={`starter-${s.key}`}
                  className="flex items-center justify-between gap-2 rounded border border-gray-200 dark:border-gray-700 px-3 py-1.5"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <Badge variant="green" size="sm">Starter</Badge>
                    <span className="min-w-0 truncate text-sm text-gray-900 dark:text-gray-100">
                      {s.name}
                    </span>
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    leftIcon={<PlusIcon className="h-4 w-4" aria-hidden="true" />}
                    aria-label={`Add starter ${s.name}`}
                    onClick={() =>
                      addItem({ source: 'starter', starterKey: s.key, name: s.name, kind: s.kind })
                    }
                  >
                    Add
                  </Button>
                </li>
              ))}
              {cloneable.map((t) => (
                <li
                  key={`tmpl-${t.id}`}
                  className="flex items-center justify-between gap-2 rounded border border-gray-200 dark:border-gray-700 px-3 py-1.5"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    {kindBadge(t.kind ?? 'questionnaire')}
                    <span className="min-w-0 truncate text-sm text-gray-900 dark:text-gray-100">
                      {t.name}
                    </span>
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    leftIcon={<PlusIcon className="h-4 w-4" aria-hidden="true" />}
                    aria-label={`Copy template ${t.name}`}
                    onClick={() =>
                      addItem({
                        source: 'clone',
                        sourceTemplateId: t.id,
                        name: `${t.name} (copy)`,
                        kind: t.kind ?? 'questionnaire',
                      })
                    }
                  >
                    Copy
                  </Button>
                </li>
              ))}
              {starters.length === 0 && cloneable.length === 0 && (
                <li className="text-sm text-gray-400 dark:text-gray-500">
                  No starters or copyable templates available.
                </li>
              )}
            </ul>
          </div>

          {/* Add a blank document */}
          <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
              Add a blank document
            </h4>
            <div className="mt-2 flex flex-wrap items-end gap-2">
              <Select
                label="Type"
                value={blankKind}
                onChange={(e) => setBlankKind(e.target.value as OnboardingDocumentKind)}
                name="blank-kind"
                options={[
                  { value: 'questionnaire', label: 'Questionnaire' },
                  { value: 'upload_request', label: 'File upload' },
                  { value: 'esign_pdf', label: 'E-sign PDF' },
                ]}
                className="w-44"
              />
              <Button
                type="button"
                variant="secondary"
                size="sm"
                leftIcon={<PlusIcon className="h-4 w-4" aria-hidden="true" />}
                onClick={() =>
                  addItem({ source: 'blank', kind: blankKind, name: '' })
                }
              >
                Add blank
              </Button>
            </div>
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500 text-pretty">
              You’ll add its questions, files, or PDF afterwards from the
              template library. A blank e-sign document needs a PDF before the
              packet can be sent.
            </p>
          </div>
        </div>
      )}

      {step === 'review' && (
        <div className="space-y-3">
          <div>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{name.trim()}</p>
            {description.trim() && (
              <p className="text-sm text-gray-500 dark:text-gray-400 text-pretty">
                {description.trim()}
              </p>
            )}
          </div>
          <ol className="divide-y divide-gray-200 dark:divide-gray-700 rounded border border-gray-200 dark:border-gray-700">
            {items.map((it, index) => (
              <li key={it.tempId} className="flex items-center gap-2 px-3 py-2">
                <span className="w-5 text-xs text-gray-400 tabular-nums">{index + 1}.</span>
                <span className="min-w-0 flex-1 truncate text-sm text-gray-900 dark:text-gray-100">
                  {it.name.trim()}
                </span>
                {kindBadge(it.kind)}
              </li>
            ))}
          </ol>
        </div>
      )}

      <ModalFooter>
        {step === 'basics' && (
          <>
            <Button variant="secondary" onClick={close}>Cancel</Button>
            <Button onClick={() => setStep('documents')} disabled={!canProceedBasics}>
              Next: documents
            </Button>
          </>
        )}
        {step === 'documents' && (
          <>
            <Button variant="secondary" onClick={() => setStep('basics')}>Back</Button>
            <Button
              onClick={() => setStep('review')}
              disabled={items.length === 0 || hasBlankName || hasDupName}
            >
              Next: review
            </Button>
          </>
        )}
        {step === 'review' && (
          <>
            <Button variant="secondary" onClick={() => setStep('documents')}>Back</Button>
            <Button
              onClick={handleCreate}
              disabled={!canCreate}
              isLoading={createMutation.isPending}
            >
              Create packet
            </Button>
          </>
        )}
      </ModalFooter>
    </Modal>
  );
}

export default OnboardingPacketWizard;

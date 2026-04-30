/**
 * Sequences page - list, create, manage sales sequences.
 * Includes sequence builder, enrollment management, and step processing.
 */

import { useState, useEffect, useMemo } from 'react';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { SearchableSelect } from '../../components/ui/SearchableSelect';
import { useContacts } from '../../hooks/useContacts';
import {
  useSequences,
  useCreateSequence,
  useUpdateSequence,
  useDeleteSequence,
  useSequenceEnrollments,
  useEnrollContact,
  usePauseEnrollment,
  useResumeEnrollment,
  useProcessDueSteps,
} from '../../hooks/useSequences';
import type {
  Sequence,
  SequenceCreate,
  SequenceUpdate,
  SequenceStep,
} from '../../types';
import {
  PlusIcon,
  TrashIcon,
  PencilSquareIcon,
  PlayIcon,
  PauseIcon,
  ArrowPathIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  EnvelopeIcon,
  ClockIcon,
  ClipboardDocumentListIcon,
  UserPlusIcon,
} from '@heroicons/react/24/outline';
import { SequenceStepBuilder } from './components/SequenceStepBuilder';
import { useContacts } from '../../hooks/useContacts';

// Step preview badge styling, keyed by SequenceStep.type.
const STEP_TYPE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  email: EnvelopeIcon,
  task: ClipboardDocumentListIcon,
  wait: ClockIcon,
};

const STEP_TYPE_COLORS: Record<string, string> = {
  email: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  task: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',
  wait: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
};

function SequenceForm({
  sequence,
  onSubmit,
  onCancel,
  isLoading,
}: {
  sequence?: Sequence;
  onSubmit: (data: SequenceCreate | SequenceUpdate) => void;
  onCancel: () => void;
  isLoading: boolean;
}) {
  const [name, setName] = useState(sequence?.name || '');
  const [description, setDescription] = useState(sequence?.description || '');
  const [steps, setSteps] = useState<SequenceStep[]>(sequence?.steps || []);
  const [isActive, setIsActive] = useState(sequence?.is_active ?? true);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({ name, description: description || undefined, steps, is_active: isActive });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="seq-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          Name
        </label>
        <input
          id="seq-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        />
      </div>
      <div>
        <label htmlFor="seq-desc" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          Description
        </label>
        <textarea
          id="seq-desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        />
      </div>
      <div>
        <span className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Steps</span>
        <SequenceStepBuilder steps={steps} onChange={setSteps} />
      </div>
      <div className="flex items-center gap-2">
        <input
          id="seq-active"
          type="checkbox"
          checked={isActive}
          onChange={(e) => setIsActive(e.target.checked)}
          className="rounded border-gray-300 dark:border-gray-600 dark:bg-gray-700 text-primary-600 focus:ring-primary-500"
        />
        <label htmlFor="seq-active" className="text-sm text-gray-700 dark:text-gray-300">
          Active
        </label>
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={isLoading}>
          {isLoading ? <Spinner size="sm" /> : sequence ? 'Update' : 'Create'}
        </Button>
      </div>
    </form>
  );
}

function EnrollmentList({
  sequenceId,
  contactById,
}: {
  sequenceId: number;
  contactById: Map<number, { full_name: string }>;
}) {
  const { data: enrollments, isLoading } = useSequenceEnrollments(sequenceId);
  const pauseMutation = usePauseEnrollment();
  const resumeMutation = useResumeEnrollment();

  if (isLoading) return <Spinner size="sm" />;
  if (!enrollments?.length) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">No enrollments yet.</p>;
  }

  const statusColors: Record<string, string> = {
    active: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    paused: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    completed: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    cancelled: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-400',
  };

  return (
    <div className="space-y-2">
      {enrollments.map((e) => {
        const contactName = contactById.get(e.contact_id)?.full_name ?? `Contact #${e.contact_id}`;
        return (
        <div
          key={e.id}
          className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700 rounded-lg"
        >
          <div>
            <p className="text-sm text-gray-900 dark:text-gray-100">
              {contactName} — Step {e.current_step}
            </p>
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                statusColors[e.status] || 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
              }`}
            >
              {e.status}
            </span>
          </div>
          <div className="flex gap-1">
            {e.status === 'active' && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => pauseMutation.mutate(e.id)}
                disabled={pauseMutation.isPending}
                aria-label="Pause enrollment"
              >
                <PauseIcon className="h-4 w-4" aria-hidden="true" />
              </Button>
            )}
            {e.status === 'paused' && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => resumeMutation.mutate(e.id)}
                disabled={resumeMutation.isPending}
                aria-label="Resume enrollment"
              >
                <PlayIcon className="h-4 w-4" aria-hidden="true" />
              </Button>
            )}
          </div>
        </div>
        );
      })}
    </div>
  );
}

function EnrollModal({
  sequenceId,
  onClose,
}: {
  sequenceId: number;
  onClose: () => void;
}) {
  const [contactId, setContactId] = useState<number | null>(null);
  const enrollMutation = useEnrollContact();
  const { data: contactsData } = useContacts({ page_size: 200 });

  const contactOptions = useMemo(
    () =>
      (contactsData?.items ?? []).map((c) => ({
        value: c.id,
        label: c.email ? `${c.full_name} — ${c.email}` : c.full_name,
      })),
    [contactsData]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (contactId === null) return;
    enrollMutation.mutate(
      { sequenceId, contactId },
      { onSuccess: () => onClose() }
    );
  };

  return (
    <div className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800">
      <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">Enroll Contact</h4>
      <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-2 sm:items-end">
        <div className="flex-1">
          <SearchableSelect
            id="enroll-contact-picker"
            label="Contact"
            value={contactId}
            onChange={setContactId}
            options={contactOptions}
            placeholder="Search contacts by name or email..."
          />
        </div>
        <div className="flex gap-2">
          <Button
            type="submit"
            size="sm"
            disabled={contactId === null || enrollMutation.isPending}
          >
            {enrollMutation.isPending ? <Spinner size="sm" /> : 'Enroll'}
          </Button>
          <Button type="button" variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </form>
    </div>
  );
}

function SequencesPage() {
  const { data: sequences, isLoading } = useSequences();
  const createMutation = useCreateSequence();
  const updateMutation = useUpdateSequence();
  const deleteMutation = useDeleteSequence();
  const processMutation = useProcessDueSteps();
  const [showForm, setShowForm] = useState(false);
  const [editingSequence, setEditingSequence] = useState<Sequence | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [enrollingId, setEnrollingId] = useState<number | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; sequence: Sequence | null }>({
    isOpen: false,
    sequence: null,
  });
  const [bannerVisible, setBannerVisible] = useState(false);

  useEffect(() => {
    if (processMutation.isSuccess) {
      setBannerVisible(true);
      const timer = setTimeout(() => setBannerVisible(false), 5000);
      return () => clearTimeout(timer);
    }
  }, [processMutation.isSuccess]);

  const { data: contactsData } = useContacts({ page_size: 1000 });
  const contactById = useMemo(
    () => new Map((contactsData?.items ?? []).map((c) => [c.id, c] as const)),
    [contactsData]
  );

  const handleCreate = (data: SequenceCreate | SequenceUpdate) => {
    createMutation.mutate(data as SequenceCreate, {
      onSuccess: () => setShowForm(false),
    });
  };

  const handleUpdate = (data: SequenceCreate | SequenceUpdate) => {
    if (!editingSequence) return;
    updateMutation.mutate(
      { id: editingSequence.id, data: data as SequenceUpdate },
      { onSuccess: () => setEditingSequence(null) }
    );
  };

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">
            Sales Sequences
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            Automate multi-step outreach to contacts
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<ArrowPathIcon className="h-4 w-4" />}
            onClick={() => processMutation.mutate()}
            disabled={processMutation.isPending}
          >
            {processMutation.isPending ? 'Processing...' : 'Process Due'}
          </Button>
          <Button
            size="sm"
            leftIcon={<PlusIcon className="h-4 w-4" />}
            onClick={() => {
              setShowForm(true);
              setEditingSequence(null);
            }}
          >
            New Sequence
          </Button>
        </div>
      </div>

      {showForm && !editingSequence && (
        <Card>
          <CardHeader title="Create Sequence" />
          <CardBody className="p-4 sm:p-6">
            <SequenceForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              isLoading={createMutation.isPending}
            />
          </CardBody>
        </Card>
      )}

      {isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner size="lg" />
        </div>
      ) : !sequences?.length ? (
        <Card>
          <CardBody className="p-8 text-center">
            <p className="text-gray-500 dark:text-gray-400">
              No sequences yet. Create your first sequence to start automating outreach.
            </p>
          </CardBody>
        </Card>
      ) : (
        <div className="space-y-4">
          {sequences.map((seq) => (
            <Card key={seq.id}>
              {editingSequence?.id === seq.id ? (
                <>
                  <CardHeader title="Edit Sequence" />
                  <CardBody className="p-4 sm:p-6">
                    <SequenceForm
                      sequence={seq}
                      onSubmit={handleUpdate}
                      onCancel={() => setEditingSequence(null)}
                      isLoading={updateMutation.isPending}
                    />
                  </CardBody>
                </>
              ) : (
                <>
                  <div className="flex items-center justify-between p-4 sm:px-6">
                    <div className="flex items-center gap-3">
                      <span
                        className={`inline-block h-2.5 w-2.5 rounded-full ${
                          seq.is_active ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'
                        }`}
                      />
                      <div>
                        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {seq.name}
                        </h3>
                        {seq.description && (
                          <p className="text-xs text-gray-500 dark:text-gray-400">{seq.description}</p>
                        )}
                        <p className="text-xs text-gray-400 dark:text-gray-500">
                          {seq.steps.length} step{seq.steps.length !== 1 ? 's' : ''}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEnrollingId(enrollingId === seq.id ? null : seq.id)}
                        aria-label="Enroll contact"
                      >
                        <UserPlusIcon className="h-4 w-4" aria-hidden="true" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditingSequence(seq)}
                        aria-label="Edit sequence"
                      >
                        <PencilSquareIcon className="h-4 w-4" aria-hidden="true" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDeleteConfirm({ isOpen: true, sequence: seq })}
                        aria-label="Delete sequence"
                      >
                        <TrashIcon className="h-4 w-4 text-red-500" aria-hidden="true" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setExpandedId(expandedId === seq.id ? null : seq.id)
                        }
                        aria-label={expandedId === seq.id ? 'Collapse' : 'Expand'}
                      >
                        {expandedId === seq.id ? (
                          <ChevronUpIcon className="h-4 w-4" aria-hidden="true" />
                        ) : (
                          <ChevronDownIcon className="h-4 w-4" aria-hidden="true" />
                        )}
                      </Button>
                    </div>
                  </div>

                  {/* Steps preview */}
                  <div className="px-4 sm:px-6 pb-3">
                    <div className="flex items-center gap-1 overflow-x-auto">
                      {seq.steps.map((step, i) => {
                        const Icon = STEP_TYPE_ICONS[step.type] || ClockIcon;
                        return (
                          <div key={i} className="flex items-center gap-1 flex-shrink-0">
                            {i > 0 && (
                              <div className="w-4 h-px bg-gray-300 dark:bg-gray-600" />
                            )}
                            <div
                              className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${
                                STEP_TYPE_COLORS[step.type] || 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
                              }`}
                            >
                              <Icon className="h-3 w-3" aria-hidden="true" />
                              {step.type}
                              {step.delay_days > 0 && ` +${step.delay_days}d`}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {enrollingId === seq.id && (
                    <div className="px-4 sm:px-6 pb-3">
                      <EnrollModal
                        sequenceId={seq.id}
                        onClose={() => setEnrollingId(null)}
                      />
                    </div>
                  )}

                  {expandedId === seq.id && (
                    <div className="border-t border-gray-200 dark:border-gray-700 p-4 sm:px-6">
                      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                        Enrollments
                      </h4>
                      <EnrollmentList sequenceId={seq.id} contactById={contactById} />
                    </div>
                  )}
                </>
              )}
            </Card>
          ))}
        </div>
      )}

      {bannerVisible && processMutation.isSuccess && processMutation.data && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-4 right-4 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg p-3 shadow-lg"
        >
          <p className="text-sm text-green-800 dark:text-green-300">
            Processed {processMutation.data.processed} due step
            {processMutation.data.processed !== 1 ? 's' : ''}.
          </p>
        </div>
      )}

      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={() => setDeleteConfirm({ isOpen: false, sequence: null })}
        onConfirm={() => {
          if (deleteConfirm.sequence) {
            deleteMutation.mutate(deleteConfirm.sequence.id, {
              onSuccess: () => setDeleteConfirm({ isOpen: false, sequence: null }),
              onError: () => setDeleteConfirm({ isOpen: false, sequence: null }),
            });
          }
        }}
        title="Delete Sequence"
        message={`Are you sure you want to delete "${deleteConfirm.sequence?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}

export default SequencesPage;

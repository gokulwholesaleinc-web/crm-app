/**
 * Sequences page - list, create, manage sales sequences.
 * Includes sequence builder, enrollment management, and step processing.
 */

import { useState } from 'react';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
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
  SequenceEnrollment,
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

const STEP_TYPE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  email: EnvelopeIcon,
  wait: ClockIcon,
  task: ClipboardDocumentListIcon,
};

const STEP_TYPE_COLORS: Record<string, string> = {
  email: 'bg-blue-100 text-blue-700',
  wait: 'bg-yellow-100 text-yellow-700',
  task: 'bg-purple-100 text-purple-700',
};

function StepBuilder({
  steps,
  onChange,
}: {
  steps: SequenceStep[];
  onChange: (steps: SequenceStep[]) => void;
}) {
  const addStep = (type: 'email' | 'task' | 'wait') => {
    const newStep: SequenceStep = {
      step_number: steps.length,
      type,
      delay_days: type === 'wait' ? 1 : 0,
      ...(type === 'email' ? { template_id: undefined } : {}),
      ...(type === 'task' ? { task_description: '' } : {}),
    };
    onChange([...steps, newStep]);
  };

  const updateStep = (index: number, updates: Partial<SequenceStep>) => {
    const updated = steps.map((s, i) => (i === index ? { ...s, ...updates } : s));
    onChange(updated);
  };

  const removeStep = (index: number) => {
    const updated = steps
      .filter((_, i) => i !== index)
      .map((s, i) => ({ ...s, step_number: i }));
    onChange(updated);
  };

  return (
    <div className="space-y-3">
      {steps.map((step, index) => {
        const Icon = STEP_TYPE_ICONS[step.type] || ClockIcon;
        return (
          <div
            key={index}
            className="flex items-start gap-3 p-3 border border-gray-200 rounded-lg"
          >
            <div
              className={`flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center ${
                STEP_TYPE_COLORS[step.type] || 'bg-gray-100 text-gray-600'
              }`}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
            </div>
            <div className="flex-1 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-900">
                  Step {index + 1}: {step.type.charAt(0).toUpperCase() + step.type.slice(1)}
                </span>
                <button
                  type="button"
                  onClick={() => removeStep(index)}
                  className="text-gray-400 hover:text-red-500"
                  aria-label={`Remove step ${index + 1}`}
                >
                  <TrashIcon className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-gray-500">Delay (days)</label>
                  <input
                    type="number"
                    min="0"
                    value={step.delay_days}
                    onChange={(e) =>
                      updateStep(index, { delay_days: parseInt(e.target.value, 10) || 0 })
                    }
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
                  />
                </div>
                {step.type === 'email' && (
                  <div>
                    <label className="block text-xs text-gray-500">Template ID</label>
                    <input
                      type="number"
                      min="1"
                      value={step.template_id || ''}
                      onChange={(e) =>
                        updateStep(index, {
                          template_id: e.target.value ? parseInt(e.target.value, 10) : undefined,
                        })
                      }
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
                    />
                  </div>
                )}
                {step.type === 'task' && (
                  <div>
                    <label className="block text-xs text-gray-500">Task Description</label>
                    <input
                      type="text"
                      value={step.task_description || ''}
                      onChange={(e) =>
                        updateStep(index, { task_description: e.target.value })
                      }
                      className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
      <div className="flex gap-2">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          leftIcon={<EnvelopeIcon className="h-4 w-4" />}
          onClick={() => addStep('email')}
        >
          Email
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          leftIcon={<ClockIcon className="h-4 w-4" />}
          onClick={() => addStep('wait')}
        >
          Wait
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          leftIcon={<ClipboardDocumentListIcon className="h-4 w-4" />}
          onClick={() => addStep('task')}
        >
          Task
        </Button>
      </div>
    </div>
  );
}

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
        <label htmlFor="seq-name" className="block text-sm font-medium text-gray-700">
          Name
        </label>
        <input
          id="seq-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        />
      </div>
      <div>
        <label htmlFor="seq-desc" className="block text-sm font-medium text-gray-700">
          Description
        </label>
        <textarea
          id="seq-desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        />
      </div>
      <div>
        <span className="block text-sm font-medium text-gray-700 mb-2">Steps</span>
        <StepBuilder steps={steps} onChange={setSteps} />
      </div>
      <div className="flex items-center gap-2">
        <input
          id="seq-active"
          type="checkbox"
          checked={isActive}
          onChange={(e) => setIsActive(e.target.checked)}
          className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
        />
        <label htmlFor="seq-active" className="text-sm text-gray-700">
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

function EnrollmentList({ sequenceId }: { sequenceId: number }) {
  const { data: enrollments, isLoading } = useSequenceEnrollments(sequenceId);
  const pauseMutation = usePauseEnrollment();
  const resumeMutation = useResumeEnrollment();

  if (isLoading) return <Spinner size="sm" />;
  if (!enrollments?.length) {
    return <p className="text-sm text-gray-500">No enrollments yet.</p>;
  }

  const statusColors: Record<string, string> = {
    active: 'bg-green-100 text-green-700',
    paused: 'bg-yellow-100 text-yellow-700',
    completed: 'bg-blue-100 text-blue-700',
    cancelled: 'bg-gray-100 text-gray-700',
  };

  return (
    <div className="space-y-2">
      {enrollments.map((e) => (
        <div
          key={e.id}
          className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
        >
          <div>
            <p className="text-sm text-gray-900">
              Contact #{e.contact_id} - Step {e.current_step}
            </p>
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                statusColors[e.status] || 'bg-gray-100 text-gray-600'
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
      ))}
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
  const [contactId, setContactId] = useState('');
  const enrollMutation = useEnrollContact();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const id = parseInt(contactId, 10);
    if (isNaN(id)) return;
    enrollMutation.mutate(
      { sequenceId, contactId: id },
      { onSuccess: () => onClose() }
    );
  };

  return (
    <div className="p-4 border border-gray-200 rounded-lg bg-white">
      <h4 className="text-sm font-medium text-gray-900 mb-3">Enroll Contact</h4>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="flex-1">
          <label htmlFor="enroll-contact-id" className="sr-only">
            Contact ID
          </label>
          <input
            id="enroll-contact-id"
            type="number"
            min="1"
            value={contactId}
            onChange={(e) => setContactId(e.target.value)}
            placeholder="Contact ID"
            required
            className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
          />
        </div>
        <Button type="submit" size="sm" disabled={enrollMutation.isPending}>
          {enrollMutation.isPending ? <Spinner size="sm" /> : 'Enroll'}
        </Button>
        <Button type="button" variant="secondary" size="sm" onClick={onClose}>
          Cancel
        </Button>
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
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900">
            Sales Sequences
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-gray-500">
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
            <p className="text-gray-500">
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
                          seq.is_active ? 'bg-green-500' : 'bg-gray-300'
                        }`}
                      />
                      <div>
                        <h3 className="text-sm font-medium text-gray-900">
                          {seq.name}
                        </h3>
                        {seq.description && (
                          <p className="text-xs text-gray-500">{seq.description}</p>
                        )}
                        <p className="text-xs text-gray-400">
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
                        onClick={() => {
                          if (window.confirm('Delete this sequence?')) {
                            deleteMutation.mutate(seq.id);
                          }
                        }}
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
                              <div className="w-4 h-px bg-gray-300" />
                            )}
                            <div
                              className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${
                                STEP_TYPE_COLORS[step.type] || 'bg-gray-100 text-gray-600'
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
                    <div className="border-t border-gray-200 p-4 sm:px-6">
                      <h4 className="text-sm font-medium text-gray-700 mb-3">
                        Enrollments
                      </h4>
                      <EnrollmentList sequenceId={seq.id} />
                    </div>
                  )}
                </>
              )}
            </Card>
          ))}
        </div>
      )}

      {processMutation.isSuccess && processMutation.data && (
        <div className="fixed bottom-4 right-4 bg-green-50 border border-green-200 rounded-lg p-3 shadow-lg">
          <p className="text-sm text-green-800">
            Processed {processMutation.data.processed} due step
            {processMutation.data.processed !== 1 ? 's' : ''}.
          </p>
        </div>
      )}
    </div>
  );
}

export default SequencesPage;

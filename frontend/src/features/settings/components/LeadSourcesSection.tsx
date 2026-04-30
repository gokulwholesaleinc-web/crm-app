import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import {
  useLeadSources,
  useCreateLeadSource,
  useUpdateLeadSource,
  useDeleteLeadSource,
} from '../../../hooks/useLeads';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Spinner } from '../../../components/ui/Spinner';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { Modal, ModalFooter } from '../../../components/ui/Modal';
import { FormInput } from '../../../components/forms';
import { PlusIcon, TrashIcon } from '@heroicons/react/24/outline';
import type {
  LeadSource,
  LeadSourceCreate,
  LeadSourceUpdate,
} from '../../../types';

interface SourceFormData {
  name: string;
  description: string;
  is_active: boolean;
}

interface SourceModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  initialData?: SourceFormData;
  onSubmit: (data: SourceFormData) => Promise<void>;
  isPending: boolean;
  isError: boolean;
}

const DEFAULTS: SourceFormData = { name: '', description: '', is_active: true };

function SourceModal({
  isOpen,
  onClose,
  title,
  initialData,
  onSubmit,
  isPending,
  isError,
}: SourceModalProps) {
  const [success, setSuccess] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
    setValue,
  } = useForm<SourceFormData>({ defaultValues: initialData || DEFAULTS });

  const isActive = watch('is_active');

  useEffect(() => {
    if (isOpen) {
      reset(initialData || DEFAULTS);
      setSuccess(false);
    }
  }, [isOpen, initialData, reset]);

  const handleFormSubmit = async (data: SourceFormData) => {
    try {
      await onSubmit(data);
      setSuccess(true);
      setTimeout(() => {
        onClose();
        setSuccess(false);
      }, 800);
    } catch {
      // error surfaced by parent via isError
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="md">
      <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-4">
        {isError && (
          <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-3">
            <p className="text-sm text-red-800 dark:text-red-300">
              Failed to save lead source. Please try again.
            </p>
          </div>
        )}
        {success && (
          <div className="rounded-md bg-green-50 dark:bg-green-900/20 p-3">
            <p className="text-sm text-green-800 dark:text-green-300">
              Lead source saved successfully!
            </p>
          </div>
        )}

        <FormInput
          label="Source Name"
          name="name"
          required
          register={register('name', { required: 'Source name is required' })}
          error={errors.name?.message}
          placeholder="e.g., Website, Referral, Trade Show"
        />

        <FormInput
          label="Description"
          name="description"
          register={register('description')}
          placeholder="Optional description"
        />

        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input
            type="checkbox"
            className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            checked={isActive}
            onChange={(e) => setValue('is_active', e.target.checked)}
          />
          Active — show this source when assigning leads
        </label>

        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose} disabled={isPending}>
            Cancel
          </Button>
          <Button type="submit" isLoading={isPending} disabled={success}>
            Save
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

export function LeadSourcesSection() {
  // active_only=false so admins can see and re-activate disabled sources here.
  const { data: sources, isLoading } = useLeadSources(false);
  const createMutation = useCreateLeadSource();
  const updateMutation = useUpdateLeadSource();
  const deleteMutation = useDeleteLeadSource();
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<LeadSource | null>(null);
  const [deletingSource, setDeletingSource] = useState<LeadSource | null>(null);

  return (
    <Card>
      <CardHeader
        title="Lead Sources"
        description="Manage where your leads come from"
        action={
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<PlusIcon className="h-4 w-4" />}
            onClick={() => setIsAddModalOpen(true)}
          >
            Add Source
          </Button>
        }
      />
      <CardBody className="p-4 sm:p-6">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Spinner size="md" />
          </div>
        ) : !sources || sources.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-4">
            No lead sources configured.
          </p>
        ) : (
          <div className="space-y-2">
            {sources.map((source) => (
              <div
                key={source.id}
                className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {source.name}
                    </p>
                    {source.description && (
                      <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                        {source.description}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                  {!source.is_active && (
                    <Badge variant="yellow" size="sm">
                      Inactive
                    </Badge>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditingSource(source)}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeletingSource(source)}
                    className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                    aria-label={`Delete ${source.name}`}
                  >
                    <TrashIcon className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardBody>

      {/* Add Source Modal */}
      <SourceModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title="Add Lead Source"
        onSubmit={async (data) => {
          const payload: LeadSourceCreate = {
            name: data.name,
            description: data.description || undefined,
            is_active: data.is_active,
          };
          await createMutation.mutateAsync(payload);
        }}
        isPending={createMutation.isPending}
        isError={createMutation.isError}
      />

      {/* Edit Source Modal */}
      {editingSource && (
        <SourceModal
          isOpen={!!editingSource}
          onClose={() => setEditingSource(null)}
          title="Edit Lead Source"
          initialData={{
            name: editingSource.name,
            description: editingSource.description || '',
            is_active: editingSource.is_active,
          }}
          onSubmit={async (data) => {
            const payload: LeadSourceUpdate = {
              name: data.name,
              description: data.description || null,
              is_active: data.is_active,
            };
            await updateMutation.mutateAsync({ id: editingSource.id, data: payload });
          }}
          isPending={updateMutation.isPending}
          isError={updateMutation.isError}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deletingSource && (
        <Modal
          isOpen={!!deletingSource}
          onClose={() => {
            setDeletingSource(null);
            deleteMutation.reset();
          }}
          title="Delete Lead Source"
          size="sm"
        >
          <div className="space-y-4">
            <p className="text-sm text-gray-700 dark:text-gray-300">
              Are you sure you want to delete{' '}
              <strong>{deletingSource.name}</strong>? This cannot be undone.
            </p>
            {deleteMutation.isError && (
              <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-3">
                <p className="text-sm text-red-800 dark:text-red-300">
                  {(deleteMutation.error as Error)?.message?.includes('409')
                    ? `Cannot delete: leads still reference this source. Reassign or delete those leads first.`
                    : 'Failed to delete source. Please try again.'}
                </p>
              </div>
            )}
            <ModalFooter>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setDeletingSource(null);
                  deleteMutation.reset();
                }}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="danger"
                isLoading={deleteMutation.isPending}
                onClick={async () => {
                  try {
                    await deleteMutation.mutateAsync(deletingSource.id);
                    setDeletingSource(null);
                  } catch {
                    // error rendered above
                  }
                }}
              >
                Delete
              </Button>
            </ModalFooter>
          </div>
        </Modal>
      )}
    </Card>
  );
}

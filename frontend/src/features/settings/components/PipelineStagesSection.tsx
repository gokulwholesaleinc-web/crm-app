import { useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import {
  usePipelineStages,
  useCreatePipelineStage,
  useUpdatePipelineStage,
  useDeletePipelineStage,
} from '../../../hooks/useOpportunities';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Spinner } from '../../../components/ui/Spinner';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { Modal, ModalFooter } from '../../../components/ui/Modal';
import { FormInput } from '../../../components/forms';
import { FormModal } from '../../../components/shared/FormModal';
import { PlusIcon, TrashIcon } from '@heroicons/react/24/outline';
import type {
  PipelineStage,
  PipelineStageCreate,
  PipelineStageUpdate,
} from '../../../types';

interface StageFormData {
  name: string;
  description: string;
  color: string;
  probability: string;
  is_won: boolean;
  is_lost: boolean;
  pipeline_type: string;
}

const STAGE_DEFAULTS: StageFormData = {
  name: '',
  description: '',
  color: '#6366f1',
  probability: '0',
  is_won: false,
  is_lost: false,
  pipeline_type: 'opportunity',
};

function StageFormFields({ register, formState: { errors }, watch, setValue }: UseFormReturn<StageFormData>) {
  const isWon = watch('is_won');
  const isLost = watch('is_lost');
  const pipelineType = watch('pipeline_type');
  return (
    <>
      <FormInput
        label="Stage Name"
        name="name"
        required
        register={register('name', { required: 'Stage name is required' })}
        error={errors.name?.message}
        placeholder="e.g., Discovery..."
      />
      <FormInput
        label="Description"
        name="description"
        register={register('description')}
        placeholder="Optional description"
      />
      <div className="grid grid-cols-2 gap-4">
        <FormInput
          label="Color"
          name="color"
          type="color"
          register={register('color')}
        />
        <FormInput
          label="Win Probability (%)"
          name="probability"
          type="number"
          register={register('probability', {
            required: 'Probability is required',
            min: { value: 0, message: 'Min 0' },
            max: { value: 100, message: 'Max 100' },
          })}
          error={errors.probability?.message}
        />
      </div>
      <div>
        <label htmlFor="stage-pipeline-type" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Pipeline Side
        </label>
        <select
          id="stage-pipeline-type"
          value={pipelineType}
          onChange={(e) => setValue('pipeline_type', e.target.value)}
          className="block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm dark:bg-gray-700 dark:text-gray-100"
        >
          <option value="lead">Lead (left side)</option>
          <option value="opportunity">Opportunity (right side)</option>
        </select>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Controls which side of the pipeline board this stage appears on.
        </p>
      </div>
      <div className="flex gap-4">
        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input
            type="checkbox"
            className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            checked={isWon}
            onChange={(e) => {
              setValue('is_won', e.target.checked);
              if (e.target.checked) setValue('is_lost', false);
            }}
          />
          Won Stage
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input
            type="checkbox"
            className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            checked={isLost}
            onChange={(e) => {
              setValue('is_lost', e.target.checked);
              if (e.target.checked) setValue('is_won', false);
            }}
          />
          Lost Stage
        </label>
      </div>
    </>
  );
}

export function PipelineStagesSection() {
  const { data: stages, isLoading } = usePipelineStages(false);
  const createMutation = useCreatePipelineStage();
  const updateMutation = useUpdatePipelineStage();
  const deleteMutation = useDeletePipelineStage();
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingStage, setEditingStage] = useState<PipelineStage | null>(null);
  const [deletingStage, setDeletingStage] = useState<PipelineStage | null>(null);

  return (
    <Card>
      <CardHeader
        title="Pipeline Stages"
        description="Manage your lead and opportunity pipeline stages"
        action={
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<PlusIcon className="h-4 w-4" />}
            onClick={() => setIsAddModalOpen(true)}
          >
            Add Stage
          </Button>
        }
      />
      <CardBody className="p-4 sm:p-6">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Spinner size="md" />
          </div>
        ) : !stages || stages.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-4">No pipeline stages configured.</p>
        ) : (
          <div className="space-y-2">
            {stages.map((stage) => (
              <div
                key={stage.id}
                className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div
                    className="h-3 w-3 rounded-full flex-shrink-0"
                    style={{ backgroundColor: stage.color }}
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{stage.name}</p>
                    {stage.description && (
                      <p className="text-xs text-gray-500 truncate">{stage.description}</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                  <Badge variant={stage.pipeline_type === 'lead' ? 'blue' : 'purple'} size="sm">
                    {stage.pipeline_type === 'lead' ? 'Lead' : 'Opportunity'}
                  </Badge>
                  <Badge variant={stage.is_won ? 'green' : stage.is_lost ? 'red' : 'gray'} size="sm">
                    {stage.probability}%
                  </Badge>
                  {!stage.is_active && (
                    <Badge variant="yellow" size="sm">Inactive</Badge>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditingStage(stage)}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeletingStage(stage)}
                    className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                    aria-label={`Delete ${stage.name}`}
                  >
                    <TrashIcon className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardBody>

      <FormModal<StageFormData>
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title="Add Pipeline Stage"
        defaultValues={STAGE_DEFAULTS}
        onSubmit={async (data) => {
          const stageData: PipelineStageCreate = {
            name: data.name,
            description: data.description || undefined,
            color: data.color,
            probability: parseInt(data.probability, 10),
            is_won: data.is_won,
            is_lost: data.is_lost,
            pipeline_type: data.pipeline_type,
          };
          await createMutation.mutateAsync(stageData);
        }}
        isPending={createMutation.isPending}
        isError={createMutation.isError}
        errorMessage="Failed to save stage. Please try again."
      >
        {(form) => <StageFormFields {...form} />}
      </FormModal>

      {deletingStage && (
        <Modal isOpen={true} onClose={() => setDeletingStage(null)} title="Delete Pipeline Stage" size="sm">
          <div className="space-y-4">
            <p className="text-sm text-gray-700 dark:text-gray-300">
              Are you sure you want to delete <strong>{deletingStage.name}</strong>? This cannot be undone.
            </p>
            {deleteMutation.isError && (
              <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-3">
                <p className="text-sm text-red-800 dark:text-red-300">
                  {(deleteMutation.error as Error)?.message?.includes('409')
                    ? `Cannot delete: opportunities still use this stage. Move them first.`
                    : 'Failed to delete stage. It may still have opportunities assigned.'}
                </p>
              </div>
            )}
            <ModalFooter>
              <Button type="button" variant="secondary" onClick={() => { setDeletingStage(null); deleteMutation.reset(); }}>
                Cancel
              </Button>
              <Button
                type="button"
                variant="danger"
                isLoading={deleteMutation.isPending}
                onClick={async () => {
                  try {
                    await deleteMutation.mutateAsync(deletingStage.id);
                    setDeletingStage(null);
                  } catch {
                    // error shown in modal
                  }
                }}
              >
                Delete
              </Button>
            </ModalFooter>
          </div>
        </Modal>
      )}

      {editingStage && (
        <FormModal<StageFormData>
          isOpen={true}
          onClose={() => setEditingStage(null)}
          title="Edit Pipeline Stage"
          defaultValues={{
            name: editingStage.name,
            description: editingStage.description || '',
            color: editingStage.color,
            probability: String(editingStage.probability),
            is_won: editingStage.is_won,
            is_lost: editingStage.is_lost,
            pipeline_type: editingStage.pipeline_type || 'opportunity',
          }}
          onSubmit={async (data) => {
            const stageData: PipelineStageUpdate = {
              name: data.name,
              description: data.description || undefined,
              color: data.color,
              probability: parseInt(data.probability, 10),
              is_won: data.is_won,
              is_lost: data.is_lost,
              pipeline_type: data.pipeline_type,
            };
            await updateMutation.mutateAsync({ id: editingStage.id, data: stageData });
          }}
          isPending={updateMutation.isPending}
          isError={updateMutation.isError}
          errorMessage="Failed to save stage. Please try again."
        >
          {(form) => <StageFormFields {...form} />}
        </FormModal>
      )}
    </Card>
  );
}

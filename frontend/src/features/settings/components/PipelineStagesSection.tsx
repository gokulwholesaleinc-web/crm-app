import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import {
  usePipelineStages,
  useCreatePipelineStage,
  useUpdatePipelineStage,
} from '../../../hooks/useOpportunities';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Spinner } from '../../../components/ui/Spinner';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { Modal, ModalFooter } from '../../../components/ui/Modal';
import { FormInput } from '../../../components/forms';
import { PlusIcon } from '@heroicons/react/24/outline';
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
}

interface StageModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  initialData?: StageFormData;
  onSubmit: (data: StageFormData) => Promise<void>;
  isPending: boolean;
  isError: boolean;
}

function StageModal({ isOpen, onClose, title, initialData, onSubmit, isPending, isError }: StageModalProps) {
  const [success, setSuccess] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
    setValue,
  } = useForm<StageFormData>({
    defaultValues: initialData || {
      name: '',
      description: '',
      color: '#6366f1',
      probability: '0',
      is_won: false,
      is_lost: false,
    },
  });

  const isWon = watch('is_won');
  const isLost = watch('is_lost');

  useEffect(() => {
    if (isOpen) {
      reset(initialData || {
        name: '',
        description: '',
        color: '#6366f1',
        probability: '0',
        is_won: false,
        is_lost: false,
      });
      setSuccess(false);
    }
  }, [isOpen, initialData, reset]);

  const handleFormSubmit = async (data: StageFormData) => {
    try {
      await onSubmit(data);
      setSuccess(true);
      setTimeout(() => {
        onClose();
        setSuccess(false);
      }, 800);
    } catch {
      // error handled by parent
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="md">
      <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-4">
        {isError && (
          <div className="rounded-md bg-red-50 p-3">
            <p className="text-sm text-red-800">Failed to save stage. Please try again.</p>
          </div>
        )}
        {success && (
          <div className="rounded-md bg-green-50 p-3">
            <p className="text-sm text-green-800">Stage saved successfully!</p>
          </div>
        )}

        <FormInput
          label="Stage Name"
          name="name"
          required
          register={register('name', { required: 'Stage name is required' })}
          error={errors.name?.message}
          placeholder="e.g., Qualification"
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

        <div className="flex gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-700">
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
          <label className="flex items-center gap-2 text-sm text-gray-700">
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

export function PipelineStagesSection() {
  const { data: stages, isLoading } = usePipelineStages(false);
  const createMutation = useCreatePipelineStage();
  const updateMutation = useUpdatePipelineStage();
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingStage, setEditingStage] = useState<PipelineStage | null>(null);

  return (
    <Card>
      <CardHeader
        title="Pipeline Stages"
        description="Manage your opportunity pipeline stages"
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
                className="flex items-center justify-between p-3 rounded-lg border border-gray-200 hover:bg-gray-50"
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
                </div>
              </div>
            ))}
          </div>
        )}
      </CardBody>

      {/* Add Stage Modal */}
      <StageModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title="Add Pipeline Stage"
        onSubmit={async (data) => {
          const stageData: PipelineStageCreate = {
            name: data.name,
            description: data.description || undefined,
            color: data.color,
            probability: parseInt(data.probability, 10),
            is_won: data.is_won,
            is_lost: data.is_lost,
          };
          await createMutation.mutateAsync(stageData);
        }}
        isPending={createMutation.isPending}
        isError={createMutation.isError}
      />

      {/* Edit Stage Modal */}
      {editingStage && (
        <StageModal
          isOpen={!!editingStage}
          onClose={() => setEditingStage(null)}
          title="Edit Pipeline Stage"
          initialData={{
            name: editingStage.name,
            description: editingStage.description || '',
            color: editingStage.color,
            probability: String(editingStage.probability),
            is_won: editingStage.is_won,
            is_lost: editingStage.is_lost,
          }}
          onSubmit={async (data) => {
            const stageData: PipelineStageUpdate = {
              name: data.name,
              description: data.description || undefined,
              color: data.color,
              probability: parseInt(data.probability, 10),
              is_won: data.is_won,
              is_lost: data.is_lost,
            };
            await updateMutation.mutateAsync({ id: editingStage.id, data: stageData });
          }}
          isPending={updateMutation.isPending}
          isError={updateMutation.isError}
        />
      )}
    </Card>
  );
}

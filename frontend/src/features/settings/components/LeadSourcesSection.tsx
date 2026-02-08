import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import {
  useLeadSources,
  useCreateLeadSource,
} from '../../../hooks/useLeads';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Spinner } from '../../../components/ui/Spinner';
import { Button } from '../../../components/ui/Button';
import { Badge } from '../../../components/ui/Badge';
import { Modal, ModalFooter } from '../../../components/ui/Modal';
import { FormInput } from '../../../components/forms';
import { PlusIcon } from '@heroicons/react/24/outline';
import type { LeadSourceCreate } from '../../../types';

interface LeadSourceFormData {
  name: string;
  description: string;
}

export function LeadSourcesSection() {
  const { data: sources, isLoading } = useLeadSources(false);
  const createMutation = useCreateLeadSource();
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [success, setSuccess] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<LeadSourceFormData>();

  useEffect(() => {
    if (isAddModalOpen) {
      reset({ name: '', description: '' });
      setSuccess(false);
    }
  }, [isAddModalOpen, reset]);

  const onSubmit = async (data: LeadSourceFormData) => {
    try {
      const sourceData: LeadSourceCreate = {
        name: data.name,
        description: data.description || undefined,
      };
      await createMutation.mutateAsync(sourceData);
      setSuccess(true);
      setTimeout(() => {
        setIsAddModalOpen(false);
        setSuccess(false);
      }, 800);
    } catch {
      // error handled by mutation state
    }
  };

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
          <p className="text-sm text-gray-500 text-center py-4">No lead sources configured.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {sources.map((source) => (
              <Badge
                key={source.id}
                variant={source.is_active ? 'blue' : 'gray'}
                size="lg"
              >
                {source.name}
              </Badge>
            ))}
          </div>
        )}
      </CardBody>

      {/* Add Source Modal */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title="Add Lead Source"
        size="md"
      >
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {createMutation.isError && (
            <div className="rounded-md bg-red-50 p-3">
              <p className="text-sm text-red-800">Failed to create lead source. Please try again.</p>
            </div>
          )}
          {success && (
            <div className="rounded-md bg-green-50 p-3">
              <p className="text-sm text-green-800">Lead source created successfully!</p>
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

          <ModalFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsAddModalOpen(false)}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" isLoading={createMutation.isPending} disabled={success}>
              Add Source
            </Button>
          </ModalFooter>
        </form>
      </Modal>
    </Card>
  );
}

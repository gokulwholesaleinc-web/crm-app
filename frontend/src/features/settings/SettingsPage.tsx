/**
 * Settings page with user profile, AI preferences, pipeline stage management,
 * lead source management, and account settings sections.
 */

import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useAuthStore } from '../../store/authStore';
import { useUpdateProfile } from '../../hooks/useAuth';
import {
  useAIPreferences,
  useUpdateAIPreferences,
} from '../../hooks/useAI';
import {
  usePipelineStages,
  useCreatePipelineStage,
  useUpdatePipelineStage,
} from '../../hooks/useOpportunities';
import {
  useLeadSources,
  useCreateLeadSource,
} from '../../hooks/useLeads';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Avatar } from '../../components/ui/Avatar';
import { Spinner } from '../../components/ui/Spinner';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Modal, ModalFooter } from '../../components/ui/Modal';
import { FormInput, FormSelect, FormTextarea } from '../../components/forms';
import {
  UserCircleIcon,
  Cog6ToothIcon,
  BellIcon,
  ShieldCheckIcon,
  PencilSquareIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';
import type {
  UserUpdate,
  PipelineStage,
  PipelineStageCreate,
  PipelineStageUpdate,
  LeadSourceCreate,
} from '../../types';

// ============================================================================
// Profile Edit Modal
// ============================================================================

interface ProfileFormData {
  full_name: string;
  phone: string;
  job_title: string;
}

interface EditProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialData: {
    full_name: string;
    email: string;
    phone: string;
    job_title: string;
  };
}

function EditProfileModal({ isOpen, onClose, initialData }: EditProfileModalProps) {
  const updateProfileMutation = useUpdateProfile();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<ProfileFormData>({
    defaultValues: {
      full_name: initialData.full_name || '',
      phone: initialData.phone || '',
      job_title: initialData.job_title || '',
    },
  });

  useEffect(() => {
    if (isOpen) {
      reset({
        full_name: initialData.full_name || '',
        phone: initialData.phone || '',
        job_title: initialData.job_title || '',
      });
      setError(null);
      setSuccess(false);
    }
  }, [isOpen, initialData.full_name, initialData.phone, initialData.job_title, reset]);

  const onSubmit = async (data: ProfileFormData) => {
    setError(null);
    setSuccess(false);

    try {
      const updateData: UserUpdate = {
        full_name: data.full_name,
        phone: data.phone || null,
        job_title: data.job_title || null,
      };

      await updateProfileMutation.mutateAsync(updateData);
      setSuccess(true);

      setTimeout(() => {
        onClose();
        setSuccess(false);
      }, 1000);
    } catch (err: unknown) {
      const errorMessage =
        err instanceof Error
          ? err.message
          : typeof err === 'object' && err !== null && 'response' in err
          ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Failed to update profile')
          : 'An error occurred';
      setError(errorMessage);
    }
  };

  const handleClose = () => {
    reset();
    setError(null);
    setSuccess(false);
    onClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Edit Profile"
      description="Update your personal information"
      size="md"
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {error && (
          <div className="rounded-md bg-red-50 p-3">
            <p className="text-sm text-red-800">{error}</p>
          </div>
        )}

        {success && (
          <div className="rounded-md bg-green-50 p-3">
            <p className="text-sm text-green-800">Profile updated successfully!</p>
          </div>
        )}

        <FormInput
          label="Full Name"
          name="full_name"
          required
          register={register('full_name', {
            required: 'Full name is required',
            minLength: {
              value: 2,
              message: 'Full name must be at least 2 characters',
            },
          })}
          error={errors.full_name?.message}
        />

        <FormInput
          label="Email"
          name="email"
          type="email"
          value={initialData.email}
          disabled
          helperText="Email cannot be changed"
        />

        <FormInput
          label="Phone"
          name="phone"
          type="tel"
          placeholder="+1 (555) 123-4567"
          register={register('phone')}
          error={errors.phone?.message}
        />

        <FormInput
          label="Job Title"
          name="job_title"
          placeholder="e.g., Sales Manager"
          register={register('job_title')}
          error={errors.job_title?.message}
        />

        <ModalFooter>
          <Button
            type="button"
            variant="secondary"
            onClick={handleClose}
            disabled={updateProfileMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            isLoading={updateProfileMutation.isPending}
            disabled={success}
          >
            Save Changes
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

// ============================================================================
// AI Preferences Section
// ============================================================================

interface AIPreferencesFormData {
  preferred_communication_style: string;
  custom_instructions: string;
}

function AIPreferencesSection() {
  const { data: preferences, isLoading } = useAIPreferences();
  const updateMutation = useUpdateAIPreferences();
  const [isEditing, setIsEditing] = useState(false);
  const [success, setSuccess] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
  } = useForm<AIPreferencesFormData>();

  useEffect(() => {
    if (isEditing && preferences) {
      reset({
        preferred_communication_style: preferences.preferred_communication_style || 'professional',
        custom_instructions: preferences.custom_instructions || '',
      });
    }
  }, [isEditing, preferences, reset]);

  const onSubmit = async (data: AIPreferencesFormData) => {
    try {
      await updateMutation.mutateAsync({
        preferred_communication_style: data.preferred_communication_style,
        custom_instructions: data.custom_instructions || null,
      });
      setSuccess(true);
      setTimeout(() => {
        setIsEditing(false);
        setSuccess(false);
      }, 1000);
    } catch {
      // error handled by mutation state
    }
  };

  const communicationStyles = [
    { value: 'professional', label: 'Professional' },
    { value: 'casual', label: 'Casual' },
    { value: 'concise', label: 'Concise' },
    { value: 'detailed', label: 'Detailed' },
  ];

  return (
    <Card>
      <CardHeader
        title="AI Preferences"
        description="Configure how the AI assistant communicates with you"
        action={
          !isEditing ? (
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<PencilSquareIcon className="h-4 w-4" />}
              onClick={() => setIsEditing(true)}
            >
              Edit
            </Button>
          ) : undefined
        }
      />
      <CardBody className="p-4 sm:p-6">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Spinner size="md" />
          </div>
        ) : isEditing ? (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            {success && (
              <div className="rounded-md bg-green-50 p-3">
                <p className="text-sm text-green-800">Preferences saved successfully!</p>
              </div>
            )}
            {updateMutation.isError && (
              <div className="rounded-md bg-red-50 p-3">
                <p className="text-sm text-red-800">Failed to save preferences. Please try again.</p>
              </div>
            )}

            <FormSelect
              label="Communication Style"
              name="preferred_communication_style"
              options={communicationStyles}
              register={register('preferred_communication_style')}
              helperText="How should the AI assistant communicate with you?"
            />

            <FormTextarea
              label="Custom Instructions"
              name="custom_instructions"
              rows={3}
              placeholder="e.g., Always prioritize high-value deals, focus on enterprise clients..."
              register={register('custom_instructions')}
              helperText="Additional instructions for the AI assistant"
            />

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => { setIsEditing(false); setSuccess(false); }}
                disabled={updateMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                isLoading={updateMutation.isPending}
                disabled={success}
              >
                Save Preferences
              </Button>
            </div>
          </form>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-3 sm:gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-xs sm:text-sm font-medium text-gray-500">
                  Communication Style
                </label>
                <p className="mt-1 text-sm text-gray-900 capitalize">
                  {preferences?.preferred_communication_style || 'Professional'}
                </p>
              </div>
              <div>
                <label className="block text-xs sm:text-sm font-medium text-gray-500">
                  Custom Instructions
                </label>
                <p className="mt-1 text-sm text-gray-900">
                  {preferences?.custom_instructions || 'None set'}
                </p>
              </div>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

// ============================================================================
// Pipeline Stages Section
// ============================================================================

interface StageFormData {
  name: string;
  description: string;
  color: string;
  probability: string;
  is_won: boolean;
  is_lost: boolean;
}

function PipelineStagesSection() {
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

// ============================================================================
// Lead Sources Section
// ============================================================================

interface LeadSourceFormData {
  name: string;
  description: string;
}

function LeadSourcesSection() {
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

// ============================================================================
// Main Settings Page
// ============================================================================

function SettingsPage() {
  const { user, isLoading } = useAuthStore();
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Settings</h1>
        <p className="mt-1 text-xs sm:text-sm text-gray-500">
          Manage your account settings and preferences
        </p>
      </div>

      {/* User Profile Section */}
      <Card>
        <CardHeader
          title="Profile"
          description="Your personal information"
          action={
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<PencilSquareIcon className="h-4 w-4" />}
              onClick={() => setIsEditModalOpen(true)}
            >
              Edit
            </Button>
          }
        />
        <CardBody className="p-4 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-start gap-4 sm:space-x-6">
            <div className="flex justify-center sm:justify-start">
              <Avatar
                src={user?.avatar_url}
                name={user?.full_name}
                size="xl"
              />
            </div>
            <div className="flex-1 space-y-4">
              <div className="grid grid-cols-1 gap-3 sm:gap-4 sm:grid-cols-2">
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-500">
                    Full Name
                  </label>
                  <p className="mt-1 text-sm text-gray-900">
                    {user?.full_name || 'Not set'}
                  </p>
                </div>
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-500">
                    Email
                  </label>
                  <p className="mt-1 text-sm text-gray-900 break-all">
                    {user?.email || 'Not set'}
                  </p>
                </div>
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-500">
                    Phone
                  </label>
                  <p className="mt-1 text-sm text-gray-900">
                    {user?.phone || 'Not set'}
                  </p>
                </div>
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-500">
                    Job Title
                  </label>
                  <p className="mt-1 text-sm text-gray-900">
                    {user?.job_title || 'Not set'}
                  </p>
                </div>
              </div>
              <div>
                <label className="block text-xs sm:text-sm font-medium text-gray-500">
                  Member Since
                </label>
                <p className="mt-1 text-sm text-gray-900">
                  {user?.created_at
                    ? new Date(user.created_at).toLocaleDateString('en-US', {
                        year: 'numeric',
                        month: 'long',
                        day: 'numeric',
                      })
                    : 'Unknown'}
                </p>
              </div>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Edit Profile Modal */}
      {user && (
        <EditProfileModal
          isOpen={isEditModalOpen}
          onClose={() => setIsEditModalOpen(false)}
          initialData={{
            full_name: user.full_name || '',
            email: user.email || '',
            phone: user.phone || '',
            job_title: user.job_title || '',
          }}
        />
      )}

      {/* AI Preferences Section */}
      <AIPreferencesSection />

      {/* Pipeline Stages Section */}
      <PipelineStagesSection />

      {/* Lead Sources Section */}
      <LeadSourcesSection />

      {/* Account Settings Section */}
      <Card>
        <CardHeader
          title="Account Settings"
          description="Manage your account preferences"
        />
        <CardBody className="p-4 sm:p-6">
          <div className="divide-y divide-gray-200">
            {/* Notification Settings */}
            <div className="py-3 sm:py-4 first:pt-0 last:pb-0">
              <div className="flex items-start sm:items-center gap-3 sm:space-x-4">
                <div className="flex-shrink-0">
                  <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-lg bg-blue-100 flex items-center justify-center">
                    <BellIcon className="h-4 w-4 sm:h-5 sm:w-5 text-blue-600" />
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">
                    Notifications
                  </p>
                  <p className="text-xs sm:text-sm text-gray-500">
                    Configure email and push notification preferences
                  </p>
                </div>
                <div className="text-xs sm:text-sm text-gray-400 flex-shrink-0">Coming soon</div>
              </div>
            </div>

            {/* Security Settings */}
            <div className="py-3 sm:py-4 first:pt-0 last:pb-0">
              <div className="flex items-start sm:items-center gap-3 sm:space-x-4">
                <div className="flex-shrink-0">
                  <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-lg bg-green-100 flex items-center justify-center">
                    <ShieldCheckIcon className="h-4 w-4 sm:h-5 sm:w-5 text-green-600" />
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">
                    Security
                  </p>
                  <p className="text-xs sm:text-sm text-gray-500">
                    Password, two-factor authentication, and sessions
                  </p>
                </div>
                <div className="text-xs sm:text-sm text-gray-400 flex-shrink-0">Coming soon</div>
              </div>
            </div>

            {/* Preferences */}
            <div className="py-3 sm:py-4 first:pt-0 last:pb-0">
              <div className="flex items-start sm:items-center gap-3 sm:space-x-4">
                <div className="flex-shrink-0">
                  <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-lg bg-purple-100 flex items-center justify-center">
                    <Cog6ToothIcon className="h-4 w-4 sm:h-5 sm:w-5 text-purple-600" />
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">
                    Preferences
                  </p>
                  <p className="text-xs sm:text-sm text-gray-500">
                    Language, timezone, and display settings
                  </p>
                </div>
                <div className="text-xs sm:text-sm text-gray-400 flex-shrink-0">Coming soon</div>
              </div>
            </div>

            {/* Profile Settings */}
            <button
              type="button"
              className="w-full py-3 sm:py-4 first:pt-0 last:pb-0 text-left hover:bg-gray-50 -mx-4 sm:-mx-6 px-4 sm:px-6 transition-colors"
              onClick={() => setIsEditModalOpen(true)}
            >
              <div className="flex items-start sm:items-center gap-3 sm:space-x-4">
                <div className="flex-shrink-0">
                  <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-lg bg-orange-100 flex items-center justify-center">
                    <UserCircleIcon className="h-4 w-4 sm:h-5 sm:w-5 text-orange-600" />
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">
                    Edit Profile
                  </p>
                  <p className="text-xs sm:text-sm text-gray-500">
                    Update your personal information and avatar
                  </p>
                </div>
                <div className="text-xs sm:text-sm text-primary-600 font-medium flex-shrink-0">
                  Edit
                </div>
              </div>
            </button>
          </div>
        </CardBody>
      </Card>

      {/* Account Status */}
      <Card>
        <CardHeader
          title="Account Status"
          description="Your account information"
        />
        <CardBody className="p-4 sm:p-6">
          <div className="grid grid-cols-1 gap-3 sm:gap-4 sm:grid-cols-3">
            <div className="bg-gray-50 rounded-lg p-3 sm:p-4">
              <p className="text-xs sm:text-sm font-medium text-gray-500">Status</p>
              <p className="mt-1 flex items-center text-sm">
                <span
                  className={`inline-block h-2 w-2 rounded-full mr-2 ${
                    user?.is_active ? 'bg-green-500' : 'bg-red-500'
                  }`}
                />
                {user?.is_active ? 'Active' : 'Inactive'}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 sm:p-4">
              <p className="text-xs sm:text-sm font-medium text-gray-500">Role</p>
              <p className="mt-1 text-sm text-gray-900">
                {user?.is_superuser ? 'Administrator' : 'User'}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 sm:p-4">
              <p className="text-xs sm:text-sm font-medium text-gray-500">Last Login</p>
              <p className="mt-1 text-sm text-gray-900">
                {user?.last_login
                  ? new Date(user.last_login).toLocaleDateString('en-US', {
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  : 'Never'}
              </p>
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

export default SettingsPage;

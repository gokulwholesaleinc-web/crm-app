/**
 * Settings page with user profile and account settings sections.
 */

import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useAuthStore } from '../../store/authStore';
import { useUpdateProfile } from '../../hooks/useAuth';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Avatar } from '../../components/ui/Avatar';
import { Spinner } from '../../components/ui/Spinner';
import { Button } from '../../components/ui/Button';
import { Modal, ModalFooter } from '../../components/ui/Modal';
import { FormInput } from '../../components/forms';
import {
  UserCircleIcon,
  Cog6ToothIcon,
  BellIcon,
  ShieldCheckIcon,
  PencilSquareIcon,
} from '@heroicons/react/24/outline';
import type { UserUpdate } from '../../types';

// Profile edit form data
interface ProfileFormData {
  full_name: string;
  phone: string;
  job_title: string;
}

// Edit Profile Modal Component
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

  // Reset form values when modal opens or initialData changes
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

      // Close modal after a brief delay to show success message
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

      {/* User Profile Section - single column on mobile */}
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
              {/* Profile fields - single column on mobile */}
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

      {/* Account Settings Section - single column cards on mobile */}
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

      {/* Account Status - single column on mobile */}
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

import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useUpdateProfile } from '../../../hooks/useAuth';
import { Modal, ModalFooter } from '../../../components/ui/Modal';
import { Button } from '../../../components/ui/Button';
import { FormInput } from '../../../components/forms';
import type { UserUpdate } from '../../../types';

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

export function EditProfileModal({ isOpen, onClose, initialData }: EditProfileModalProps) {
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

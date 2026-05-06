import { useState, useEffect, ReactNode } from 'react';
import {
  useForm,
  FieldValues,
  DefaultValues,
  UseFormReturn,
} from 'react-hook-form';
import { Modal, ModalFooter, ModalSize } from '../ui/Modal';
import { Button } from '../ui/Button';

export interface FormModalProps<T extends FieldValues> {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  defaultValues: DefaultValues<T>;
  onSubmit: (data: T) => Promise<void>;
  isPending: boolean;
  isError: boolean;
  errorMessage: string;
  size?: ModalSize;
  submitLabel?: string;
  children: (form: UseFormReturn<T>) => ReactNode;
}

export function FormModal<T extends FieldValues>({
  isOpen,
  onClose,
  title,
  defaultValues,
  onSubmit,
  isPending,
  isError,
  errorMessage,
  size = 'md',
  submitLabel = 'Save',
  children,
}: FormModalProps<T>) {
  const [success, setSuccess] = useState(false);

  const form = useForm<T>({ defaultValues });

  useEffect(() => {
    if (isOpen) {
      form.reset(defaultValues);
      setSuccess(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const handleFormSubmit = async (data: T) => {
    try {
      await onSubmit(data);
      setSuccess(true);
      setTimeout(() => {
        onClose();
        setSuccess(false);
      }, 800);
    } catch {
      // error surfaced via isError prop
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size={size}>
      <form onSubmit={form.handleSubmit(handleFormSubmit)} className="space-y-4">
        {isError && (
          <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-3">
            <p className="text-sm text-red-800 dark:text-red-300">{errorMessage}</p>
          </div>
        )}
        {success && (
          <div className="rounded-md bg-green-50 dark:bg-green-900/20 p-3">
            <p className="text-sm text-green-800 dark:text-green-300">Saved successfully!</p>
          </div>
        )}

        {children(form)}

        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose} disabled={isPending}>
            Cancel
          </Button>
          <Button type="submit" isLoading={isPending} disabled={success}>
            {submitLabel}
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}

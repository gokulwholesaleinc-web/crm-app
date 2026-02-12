import { ReactNode } from 'react';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import { Modal } from './Modal';
import { Button } from './Button';

export interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string | ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'danger' | 'warning' | 'info';
  isLoading?: boolean;
}

const variantStyles = {
  danger: {
    icon: 'bg-red-100',
    iconColor: 'text-red-600',
    button: 'danger' as const,
  },
  warning: {
    icon: 'bg-yellow-100',
    iconColor: 'text-yellow-600',
    button: 'primary' as const,
  },
  info: {
    icon: 'bg-blue-100',
    iconColor: 'text-blue-600',
    button: 'primary' as const,
  },
};

export function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  isLoading = false,
}: ConfirmDialogProps) {
  const styles = variantStyles[variant];

  const handleConfirm = () => {
    onConfirm();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="sm"
      showCloseButton={false}
      closeOnOverlayClick={!isLoading}
    >
      <div className="sm:flex sm:items-start">
        <div
          className={`mx-auto flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full ${styles.icon} sm:mx-0 sm:h-10 sm:w-10`}
        >
          <ExclamationTriangleIcon
            className={`h-6 w-6 ${styles.iconColor}`}
            aria-hidden="true"
          />
        </div>
        <div className="mt-3 text-center sm:ml-4 sm:mt-0 sm:text-left">
          <h3 className="text-base font-semibold leading-6 text-gray-900 dark:text-gray-100">
            {title}
          </h3>
          <div className="mt-2">
            <p className="text-sm text-gray-500 dark:text-gray-400">{message}</p>
          </div>
        </div>
      </div>
      <div className="mt-5 sm:mt-4 flex flex-col-reverse sm:flex-row sm:justify-end gap-2 sm:gap-3">
        <Button
          variant="secondary"
          onClick={onClose}
          disabled={isLoading}
          className="w-full sm:w-auto min-h-[44px] sm:min-h-0"
        >
          {cancelLabel}
        </Button>
        <Button
          variant={styles.button}
          onClick={handleConfirm}
          isLoading={isLoading}
          disabled={isLoading}
          className="w-full sm:w-auto min-h-[44px] sm:min-h-0"
        >
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}

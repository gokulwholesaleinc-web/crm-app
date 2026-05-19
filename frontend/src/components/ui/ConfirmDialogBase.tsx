import { Fragment, ReactNode } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import { Button } from './Button';

export interface ConfirmDialogBaseProps {
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
    icon: 'bg-red-100 dark:bg-red-900/30',
    iconColor: 'text-red-600 dark:text-red-400',
    button: 'danger' as const,
  },
  warning: {
    icon: 'bg-yellow-100 dark:bg-yellow-900/30',
    iconColor: 'text-yellow-600 dark:text-yellow-400',
    button: 'primary' as const,
  },
  info: {
    icon: 'bg-blue-100 dark:bg-blue-900/30',
    iconColor: 'text-blue-600 dark:text-blue-400',
    button: 'primary' as const,
  },
};

export function ConfirmDialogBase({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'danger',
  isLoading = false,
}: ConfirmDialogBaseProps) {
  const styles = variantStyles[variant];

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog
        as="div"
        className="relative z-[60]"
        onClose={isLoading ? () => {} : onClose}
      >
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/30 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-150"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-sm transform overflow-hidden rounded-2xl bg-white p-4 text-left align-middle shadow-xl transition-[opacity,transform] dark:bg-gray-800 sm:p-6">
                <Dialog.Title
                  as="h3"
                  className="text-lg font-semibold leading-6 text-gray-900 dark:text-gray-100"
                >
                  {title}
                </Dialog.Title>
                <div className="mt-4 sm:flex sm:items-start">
                  <div
                    className={`mx-auto flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full ${styles.icon} sm:mx-0 sm:h-10 sm:w-10`}
                  >
                    <ExclamationTriangleIcon
                      className={`h-6 w-6 ${styles.iconColor}`}
                      aria-hidden="true"
                    />
                  </div>
                  <div className="mt-3 text-center sm:ml-4 sm:mt-0 sm:text-left">
                    <div className="text-sm text-gray-500 dark:text-gray-400">
                      {message}
                    </div>
                  </div>
                </div>
                <div className="mt-5 flex flex-col-reverse gap-2 sm:mt-4 sm:flex-row sm:justify-end sm:gap-3">
                  <Button
                    variant="secondary"
                    onClick={onClose}
                    disabled={isLoading}
                    autoFocus
                    className="w-full min-h-[44px] sm:w-auto sm:min-h-0"
                  >
                    {cancelLabel}
                  </Button>
                  <Button
                    variant={styles.button}
                    onClick={onConfirm}
                    isLoading={isLoading}
                    disabled={isLoading}
                    className="w-full min-h-[44px] sm:w-auto sm:min-h-0"
                  >
                    {confirmLabel}
                  </Button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

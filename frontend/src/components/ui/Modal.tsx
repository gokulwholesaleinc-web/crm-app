import { Fragment, ReactNode } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import clsx from 'clsx';

export type ModalSize = 'sm' | 'md' | 'lg' | 'xl' | 'full';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: ReactNode;
  size?: ModalSize;
  showCloseButton?: boolean;
  closeOnOverlayClick?: boolean;
  fullScreenOnMobile?: boolean;
}

// Mobile: full-width/height by default; Desktop: constrained by max-width
const sizeStyles: Record<ModalSize, string> = {
  sm: 'w-full h-full sm:h-auto sm:max-w-sm',
  md: 'w-full h-full sm:h-auto sm:max-w-md',
  lg: 'w-full h-full sm:h-auto sm:max-w-lg',
  xl: 'w-full h-full sm:h-auto sm:max-w-xl',
  full: 'w-full h-full sm:h-auto sm:max-w-4xl',
};

// Mobile fullscreen base styles
const mobileFullScreenStyles = 'rounded-none sm:rounded-2xl max-h-full sm:max-h-[90vh]';

export function Modal({
  isOpen,
  onClose,
  title,
  description,
  children,
  size = 'md',
  showCloseButton = true,
  closeOnOverlayClick = true,
  fullScreenOnMobile = false,
}: ModalProps) {
  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog
        as="div"
        className="relative z-50"
        onClose={closeOnOverlayClick ? onClose : () => {}}
      >
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/25 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto overscroll-contain">
          <div className={clsx(
              'flex min-h-full text-center',
              fullScreenOnMobile
                ? 'items-end sm:items-center justify-center p-0 sm:p-4'
                : 'items-center justify-center p-4'
            )}>
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel
                className={clsx(
                  'w-full transform bg-white dark:bg-gray-800 p-4 sm:p-6 text-left align-middle shadow-xl transition-all',
                  'overflow-y-auto', // Proper scroll behavior
                  sizeStyles[size],
                  fullScreenOnMobile ? mobileFullScreenStyles : 'rounded-2xl'
                )}
              >
                {(title || showCloseButton) && (
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      {title && (
                        <Dialog.Title
                          as="h3"
                          className="text-lg font-semibold leading-6 text-gray-900 dark:text-gray-100"
                        >
                          {title}
                        </Dialog.Title>
                      )}
                      {description && (
                        <Dialog.Description className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                          {description}
                        </Dialog.Description>
                      )}
                    </div>
                    {showCloseButton && (
                      <button
                        type="button"
                        className="rounded-lg p-2 sm:p-1 text-gray-400 hover:text-gray-500 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 -mr-1 sm:mr-0 min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 flex items-center justify-center"
                        onClick={onClose}
                      >
                        <span className="sr-only">Close</span>
                        <XMarkIcon className="h-6 w-6 sm:h-5 sm:w-5" aria-hidden="true" />
                      </button>
                    )}
                  </div>
                )}
                {children}
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

export interface ModalFooterProps {
  children: ReactNode;
  className?: string;
}

export function ModalFooter({ children, className }: ModalFooterProps) {
  return (
    <div
      className={clsx(
        'mt-4 sm:mt-6 flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-end gap-2 sm:gap-3',
        className
      )}
    >
      {children}
    </div>
  );
}

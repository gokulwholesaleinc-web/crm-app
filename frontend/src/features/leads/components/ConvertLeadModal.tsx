import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { CheckIcon } from '@heroicons/react/24/outline';
import { Button, Modal, ConfirmDialog } from '../../../components/ui';

interface ConvertLeadFormData {
  createCompany: boolean;
}

interface ConvertLeadModalProps {
  isOpen: boolean;
  leadId: string;
  leadName: string;
  onClose: () => void;
  onConvert: (data: ConvertLeadFormData) => Promise<void>;
}

export function ConvertLeadModal({
  isOpen,
  leadName,
  onClose,
  onConvert,
}: ConvertLeadModalProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { isDirty },
  } = useForm<ConvertLeadFormData>({
    defaultValues: {
      createCompany: true,
    },
  });

  const handleCancel = () => {
    if (isDirty) {
      setShowDiscardConfirm(true);
    } else {
      onClose();
    }
  };

  const onSubmit = async (data: ConvertLeadFormData) => {
    setIsLoading(true);
    try {
      await onConvert(data);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="lg"
      showCloseButton={false}
      closeOnOverlayClick={false}
      fullScreenOnMobile
    >
      <div className="flex flex-col h-full sm:h-auto">
        <div className="text-center">
          <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100">
            <CheckIcon className="h-6 w-6 text-green-600" aria-hidden="true" />
          </div>
          <h3 className="mt-3 text-lg leading-6 font-medium text-gray-900 dark:text-gray-100">
            Convert Lead
          </h3>
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400 px-2">
            Convert &ldquo;{leadName}&rdquo; to a contact.
          </p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4 flex-1 flex flex-col">
          <div className="flex-1 space-y-4 overflow-y-auto">
            <div className="flex items-start">
              <div className="flex items-center h-5">
                <input
                  id="createCompany"
                  type="checkbox"
                  {...register('createCompany')}
                  className="focus:ring-primary-500 h-5 w-5 sm:h-4 sm:w-4 text-primary-600 border-gray-300 rounded"
                />
              </div>
              <div className="ml-3 text-sm">
                <label
                  htmlFor="createCompany"
                  className="font-medium text-gray-700 dark:text-gray-300"
                >
                  Also create Company
                </label>
                <p className="text-gray-500">
                  Create a company from the lead&apos;s company info and link it to the new contact.
                </p>
              </div>
            </div>
          </div>

          <div className="mt-5 pt-4 border-t border-gray-200 sm:border-t-0 sm:pt-0 sm:mt-6 flex flex-col-reverse sm:grid sm:grid-cols-2 sm:gap-3 sm:grid-flow-row-dense gap-3">
            <Button
              type="submit"
              isLoading={isLoading}
              className="w-full sm:col-start-2"
            >
              Convert Lead
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={handleCancel}
              className="w-full sm:col-start-1"
            >
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </Modal>
    {/* Sibling, not child — nesting ConfirmDialog inside Modal stacks two focus traps */}
    <ConfirmDialog
      isOpen={showDiscardConfirm}
      onClose={() => setShowDiscardConfirm(false)}
      onConfirm={() => {
        reset();
        setShowDiscardConfirm(false);
        onClose();
      }}
      title="Discard changes?"
      message="Your unsaved changes will be lost."
      confirmLabel="Discard"
      cancelLabel="Keep editing"
      variant="danger"
    />
    </>
  );
}

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { CheckIcon } from '@heroicons/react/24/outline';
import { Button, Modal } from '../../../components/ui';

interface ConvertLeadFormData {
  createContact: boolean;
  createOpportunity: boolean;
  opportunityName?: string;
  opportunityValue?: number;
  opportunityStage?: string;
}

interface ConvertLeadModalProps {
  isOpen: boolean;
  leadId: string;
  leadName: string;
  onClose: () => void;
  onConvert: (data: ConvertLeadFormData) => Promise<void>;
}

const opportunityStages = [
  { value: 'qualification', label: 'Qualification' },
  { value: 'proposal', label: 'Proposal' },
  { value: 'negotiation', label: 'Negotiation' },
  { value: 'closed_won', label: 'Closed Won' },
  { value: 'closed_lost', label: 'Closed Lost' },
];

export function ConvertLeadModal({
  isOpen,
  leadName,
  onClose,
  onConvert,
}: ConvertLeadModalProps) {
  const [isLoading, setIsLoading] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<ConvertLeadFormData>({
    defaultValues: {
      createContact: true,
      createOpportunity: false,
      opportunityName: '',
      opportunityValue: 0,
      opportunityStage: 'qualification',
    },
  });

  const createOpportunity = watch('createOpportunity');

  const onSubmit = async (data: ConvertLeadFormData) => {
    setIsLoading(true);
    try {
      await onConvert(data);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="lg"
      showCloseButton={false}
    >
      <div className="text-center">
        <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100">
          <CheckIcon className="h-6 w-6 text-green-600" aria-hidden="true" />
        </div>
        <h3 className="mt-3 text-lg leading-6 font-medium text-gray-900">
          Convert Lead
        </h3>
        <p className="mt-2 text-sm text-gray-500">
          Convert "{leadName}" to a contact and/or opportunity.
        </p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4">
        {/* Create Contact Option */}
        <div className="flex items-start">
          <div className="flex items-center h-5">
            <input
              id="createContact"
              type="checkbox"
              {...register('createContact')}
              className="focus:ring-primary-500 h-4 w-4 text-primary-600 border-gray-300 rounded"
            />
          </div>
          <div className="ml-3 text-sm">
            <label
              htmlFor="createContact"
              className="font-medium text-gray-700"
            >
              Create Contact
            </label>
            <p className="text-gray-500">
              Create a new contact from this lead's information.
            </p>
          </div>
        </div>

        {/* Create Opportunity Option */}
        <div className="flex items-start">
          <div className="flex items-center h-5">
            <input
              id="createOpportunity"
              type="checkbox"
              {...register('createOpportunity')}
              className="focus:ring-primary-500 h-4 w-4 text-primary-600 border-gray-300 rounded"
            />
          </div>
          <div className="ml-3 text-sm">
            <label
              htmlFor="createOpportunity"
              className="font-medium text-gray-700"
            >
              Create Opportunity
            </label>
            <p className="text-gray-500">
              Create a new opportunity for this lead.
            </p>
          </div>
        </div>

        {/* Opportunity Details (conditional) */}
        {createOpportunity && (
          <div className="ml-7 space-y-4 border-l-2 border-gray-200 pl-4">
            <div>
              <label
                htmlFor="opportunityName"
                className="block text-sm font-medium text-gray-700"
              >
                Opportunity Name *
              </label>
              <input
                type="text"
                id="opportunityName"
                {...register('opportunityName', {
                  required: createOpportunity
                    ? 'Opportunity name is required'
                    : false,
                })}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                placeholder={`${leadName} - Opportunity`}
              />
              {errors.opportunityName && (
                <p className="mt-1 text-sm text-red-600">
                  {errors.opportunityName.message}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="opportunityValue"
                className="block text-sm font-medium text-gray-700"
              >
                Expected Value
              </label>
              <div className="mt-1 relative rounded-md shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <span className="text-gray-500 sm:text-sm">$</span>
                </div>
                <input
                  type="number"
                  id="opportunityValue"
                  {...register('opportunityValue', {
                    min: { value: 0, message: 'Value must be positive' },
                  })}
                  className="pl-7 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                  placeholder="0.00"
                />
              </div>
              {errors.opportunityValue && (
                <p className="mt-1 text-sm text-red-600">
                  {errors.opportunityValue.message}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="opportunityStage"
                className="block text-sm font-medium text-gray-700"
              >
                Stage
              </label>
              <select
                id="opportunityStage"
                {...register('opportunityStage')}
                className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
              >
                {opportunityStages.map((stage) => (
                  <option key={stage.value} value={stage.value}>
                    {stage.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* Form Actions */}
        <div className="mt-5 sm:mt-6 sm:grid sm:grid-cols-2 sm:gap-3 sm:grid-flow-row-dense">
          <Button
            type="submit"
            isLoading={isLoading}
            className="sm:col-start-2"
          >
            Convert Lead
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={onClose}
            className="mt-3 sm:mt-0 sm:col-start-1"
          >
            Cancel
          </Button>
        </div>
      </form>
    </Modal>
  );
}

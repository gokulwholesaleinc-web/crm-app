/**
 * Reusable contracts list component for contact and company detail pages.
 */

import { useState } from 'react';
import { useContracts, useCreateContract, useUpdateContract, useDeleteContract } from '../../hooks/useContracts';
import { Button, Spinner, Modal, ConfirmDialog } from '../ui';
import { formatDate, formatCurrency } from '../../utils/formatters';
import type { Contract, ContractCreate, ContractUpdate } from '../../types';
import clsx from 'clsx';

interface ContractsListProps {
  entityType: 'contact' | 'company';
  entityId: number;
}

const DEFAULT_STATUS_COLOR = { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-700 dark:text-gray-300' };

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  draft: DEFAULT_STATUS_COLOR,
  active: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-300' },
  expired: { bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-300' },
  terminated: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-300' },
};

function ContractStatusBadge({ status }: { status: string }) {
  const colors = STATUS_COLORS[status] ?? DEFAULT_STATUS_COLOR;
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium capitalize',
        colors.bg,
        colors.text
      )}
    >
      {status}
    </span>
  );
}

function ContractFormModal({
  isOpen,
  onClose,
  entityType,
  entityId,
  contract,
}: {
  isOpen: boolean;
  onClose: () => void;
  entityType: 'contact' | 'company';
  entityId: number;
  contract?: Contract;
}) {
  const createMutation = useCreateContract();
  const updateMutation = useUpdateContract();
  const isEditing = !!contract;

  const [title, setTitle] = useState(contract?.title ?? '');
  const [status, setStatus] = useState(contract?.status ?? 'draft');
  const [value, setValue] = useState(contract?.value?.toString() ?? '');
  const [currency, setCurrency] = useState(contract?.currency ?? 'USD');
  const [startDate, setStartDate] = useState(contract?.start_date ?? '');
  const [endDate, setEndDate] = useState(contract?.end_date ?? '');
  const [scope, setScope] = useState(contract?.scope ?? '');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const data: ContractCreate | ContractUpdate = {
      title,
      status,
      value: value ? parseFloat(value) : null,
      currency,
      start_date: startDate || null,
      end_date: endDate || null,
      scope: scope || null,
      ...(entityType === 'contact' ? { contact_id: entityId } : { company_id: entityId }),
    };

    if (isEditing && contract) {
      await updateMutation.mutateAsync({ id: contract.id, data: data as ContractUpdate });
    } else {
      await createMutation.mutateAsync(data as ContractCreate);
    }
    onClose();
  };

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Edit Contract' : 'Add Contract'}
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="contract-title" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Title <span className="text-red-500">*</span>
          </label>
          <input
            id="contract-title"
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm bg-white dark:bg-gray-700 dark:text-gray-100"
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="contract-status" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Status
            </label>
            <select
              id="contract-status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm bg-white dark:bg-gray-700 dark:text-gray-100"
            >
              <option value="draft">Draft</option>
              <option value="active">Active</option>
              <option value="expired">Expired</option>
              <option value="terminated">Terminated</option>
            </select>
          </div>

          <div>
            <label htmlFor="contract-value" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Value
            </label>
            <div className="mt-1 flex rounded-md shadow-sm">
              <input
                id="contract-value"
                type="number"
                step="0.01"
                min="0"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="block w-full rounded-l-md border-gray-300 dark:border-gray-600 focus:border-primary-500 focus:ring-primary-500 sm:text-sm bg-white dark:bg-gray-700 dark:text-gray-100"
              />
              <select
                aria-label="Currency"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="rounded-r-md border-l-0 border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-600 text-gray-500 dark:text-gray-300 sm:text-sm"
              >
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="GBP">GBP</option>
              </select>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="contract-start-date" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Start Date
            </label>
            <input
              id="contract-start-date"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm bg-white dark:bg-gray-700 dark:text-gray-100"
            />
          </div>

          <div>
            <label htmlFor="contract-end-date" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              End Date
            </label>
            <input
              id="contract-end-date"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm bg-white dark:bg-gray-700 dark:text-gray-100"
            />
          </div>
        </div>

        <div>
          <label htmlFor="contract-scope" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Scope
          </label>
          <textarea
            id="contract-scope"
            rows={3}
            value={scope}
            onChange={(e) => setScope(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm bg-white dark:bg-gray-700 dark:text-gray-100"
          />
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
          <Button variant="secondary" onClick={onClose} type="button">
            Cancel
          </Button>
          <Button variant="primary" type="submit" isLoading={isPending}>
            {isEditing ? 'Update' : 'Create'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export default function ContractsList({ entityType, entityId }: ContractsListProps) {
  const filterKey = entityType === 'contact' ? 'contact_id' : 'company_id';
  const { data, isLoading } = useContracts({ [filterKey]: entityId });
  const deleteMutation = useDeleteContract();

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingContract, setEditingContract] = useState<Contract | undefined>();
  const [deletingContract, setDeletingContract] = useState<Contract | undefined>();

  const contracts = data?.items ?? [];

  const handleDelete = async () => {
    if (!deletingContract) return;
    await deleteMutation.mutateAsync(deletingContract.id);
    setDeletingContract(undefined);
  };

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 flex items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden">
      <div className="px-4 py-4 border-b border-gray-200 dark:border-gray-700 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Contracts ({contracts.length})
        </h3>
        <Button
          size="sm"
          variant="primary"
          onClick={() => setShowCreateModal(true)}
          className="w-full sm:w-auto"
        >
          Add Contract
        </Button>
      </div>

      {contracts.length === 0 ? (
        <div className="text-center py-12 px-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">No contracts yet.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Title</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Value</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Start</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">End</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Scope</th>
                <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {contracts.map((contract: Contract) => (
                <tr key={contract.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-gray-100">
                    {contract.title}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <ContractStatusBadge status={contract.status} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-right font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {contract.value != null ? formatCurrency(contract.value, contract.currency) : '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    {contract.start_date ? formatDate(contract.start_date) : '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    {contract.end_date ? formatDate(contract.end_date) : '-'}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400 max-w-[200px] truncate">
                    {contract.scope ?? '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                    <button
                      onClick={() => setEditingContract(contract)}
                      className="text-primary-600 dark:text-primary-400 hover:text-primary-900 dark:hover:text-primary-300 mr-3"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => setDeletingContract(contract)}
                      className="text-red-600 dark:text-red-400 hover:text-red-900 dark:hover:text-red-300"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <ContractFormModal
          isOpen={showCreateModal}
          onClose={() => setShowCreateModal(false)}
          entityType={entityType}
          entityId={entityId}
        />
      )}

      {/* Edit Modal */}
      {editingContract && (
        <ContractFormModal
          isOpen={!!editingContract}
          onClose={() => setEditingContract(undefined)}
          entityType={entityType}
          entityId={entityId}
          contract={editingContract}
        />
      )}

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={!!deletingContract}
        onClose={() => setDeletingContract(undefined)}
        onConfirm={handleDelete}
        title="Delete Contract"
        message={`Are you sure you want to delete "${deletingContract?.title}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}

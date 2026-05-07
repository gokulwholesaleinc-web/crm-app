import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { PlusIcon } from '@heroicons/react/24/outline';
import { Button, EntityLink, Modal, ConfirmDialog, PaginationBar } from '../../components/ui';
import { SkeletonTable } from '../../components/ui/Skeleton';
import { SortableTh } from '../../components/shared/SortableTh';
import {
  useContracts,
  useCreateContract,
  useDeleteContract,
} from '../../hooks/useContracts';
import {
  useListPageSizeState,
  useListSortPersistence,
} from '../../hooks/useListPageDefaults';
import { formatDate, formatCurrency } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { showSuccess, showError } from '../../utils/toast';
import type { Contract, ContractCreate } from '../../types';
import { ContractStatusBadge } from './statusBadge';

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'draft', label: 'Draft' },
  { value: 'sent', label: 'Sent' },
  { value: 'signed', label: 'Signed' },
  { value: 'active', label: 'Active' },
  { value: 'expired', label: 'Expired' },
  { value: 'terminated', label: 'Terminated' },
];

function CreateContractModal({
  isOpen,
  onClose,
  onCreated,
}: {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (id: number) => void;
}) {
  const createMutation = useCreateContract();
  const [title, setTitle] = useState('');
  const [status, setStatus] = useState('draft');
  const [value, setValue] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [scope, setScope] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const data: ContractCreate = {
        title,
        status,
        value: value ? parseFloat(value) : null,
        currency,
        start_date: startDate || null,
        end_date: endDate || null,
        scope: scope || null,
      };
      const created = await createMutation.mutateAsync(data);
      showSuccess('Contract created');
      onCreated(created.id);
    } catch {
      showError('Failed to create contract');
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Create Contract" size="lg" fullScreenOnMobile>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="new-title" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Title <span className="text-red-500">*</span>
          </label>
          <input
            id="new-title"
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm bg-white dark:bg-gray-700 dark:text-gray-100"
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="new-status" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Status</label>
            <select
              id="new-status"
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
            <label htmlFor="new-value" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Value</label>
            <div className="mt-1 flex rounded-md shadow-sm">
              <input
                id="new-value"
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
            <label htmlFor="new-start-date" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Start Date</label>
            <input
              id="new-start-date"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm bg-white dark:bg-gray-700 dark:text-gray-100"
            />
          </div>
          <div>
            <label htmlFor="new-end-date" className="block text-sm font-medium text-gray-700 dark:text-gray-300">End Date</label>
            <input
              id="new-end-date"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm bg-white dark:bg-gray-700 dark:text-gray-100"
            />
          </div>
        </div>

        <div>
          <label htmlFor="new-scope" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Scope</label>
          <textarea
            id="new-scope"
            rows={3}
            value={scope}
            onChange={(e) => setScope(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm bg-white dark:bg-gray-700 dark:text-gray-100"
          />
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
          <Button variant="secondary" onClick={onClose} type="button">Cancel</Button>
          <Button type="submit" isLoading={createMutation.isPending} disabled={!title.trim()}>Create</Button>
        </div>
      </form>
    </Modal>
  );
}

function ContractsPage() {
  usePageTitle('Contracts');
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const searchQuery = searchParams.get('search') || '';
  const statusParam = searchParams.get('status') || '';
  const statusFilter = statusOptions.some((o) => o.value === statusParam) ? statusParam : '';

  const setSearchQuery = (q: string) =>
    setSearchParams((prev) => { if (q) prev.set('search', q); else prev.delete('search'); return prev; }, { replace: true });
  const setStatusFilter = (s: string) =>
    setSearchParams((prev) => { if (s) prev.set('status', s); else prev.delete('status'); return prev; }, { replace: true });

  const [currentPage, setCurrentPage] = useState(1);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; contract: Contract | null }>({
    isOpen: false,
    contract: null,
  });

  const { sortBy, sortDir, toggle: toggleSort } = useListSortPersistence('contracts');
  const [pageSize, setPageSize] = useListPageSizeState('contracts');

  const handleSortToggle = (field: string) => {
    setCurrentPage(1);
    toggleSort(field);
  };

  const { data, isLoading, error } = useContracts({
    page: currentPage,
    page_size: pageSize,
    search: searchQuery || undefined,
    status: statusFilter || undefined,
    ...(sortBy && { order_by: sortBy, order_dir: sortDir }),
  });

  const deleteContractMutation = useDeleteContract();

  const contracts = data?.items ?? [];
  const totalPages = data?.pages ?? 1;
  const total = data?.total ?? 0;

  const handleDeleteClick = (contract: Contract) => {
    setDeleteConfirm({ isOpen: true, contract });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm.contract) return;
    try {
      await deleteContractMutation.mutateAsync(deleteConfirm.contract.id);
      setDeleteConfirm({ isOpen: false, contract: null });
      showSuccess('Contract deleted');
    } catch {
      showError('Failed to delete contract');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Contracts</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Manage and track contracts</p>
        </div>
        <Button
          leftIcon={<PlusIcon className="h-5 w-5" />}
          onClick={() => setShowCreate(true)}
          className="w-full sm:w-auto"
        >
          New Contract
        </Button>
      </div>

      {/* Filters */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 border border-transparent dark:border-gray-700">
        <div className="flex flex-col gap-3 sm:flex-row sm:gap-4">
          <div className="flex-1">
            <label htmlFor="contract-search" className="sr-only">Search contracts</label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
              <input
                type="text"
                id="contract-search"
                autoComplete="off"
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
                className="block w-full pl-10 pr-3 py-2.5 sm:py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500 focus-visible:border-primary-500 text-base sm:text-sm"
                placeholder="Search by title..."
              />
            </div>
          </div>
          <div className="flex-1 sm:flex-none sm:w-48">
            <label htmlFor="contract-status-filter" className="sr-only">Filter by status</label>
            <select
              id="contract-status-filter"
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setCurrentPage(1); }}
              className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 py-2.5 sm:py-2 text-base sm:text-sm"
            >
              {statusOptions.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
          <p className="text-sm font-medium text-red-800 dark:text-red-300">
            {error instanceof Error ? error.message : 'An error occurred'}
          </p>
        </div>
      )}

      {/* Table */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
        {isLoading ? (
          <SkeletonTable rows={5} cols={7} />
        ) : contracts.length === 0 ? (
          <div className="text-center py-12 px-4">
            <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No contracts</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Get started by creating a new contract.</p>
            <div className="mt-6 flex justify-center">
              <Button onClick={() => setShowCreate(true)}>New Contract</Button>
            </div>
          </div>
        ) : (
          <>
            {/* Mobile cards */}
            <div className="block md:hidden divide-y divide-gray-200 dark:divide-gray-700">
              {contracts.map((contract: Contract) => (
                <div key={contract.id} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700">
                  <div className="flex items-start justify-between gap-2">
                    <Link to={`/contracts/${contract.id}`} className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300 truncate">
                        {contract.title}
                      </p>
                    </Link>
                    <ContractStatusBadge status={contract.status} />
                  </div>
                  <div className="mt-2 space-y-1 text-sm text-gray-500 dark:text-gray-400">
                    {contract.contact && (
                      <p className="truncate">
                        <EntityLink type="contact" id={contract.contact.id} variant="muted">
                          {contract.contact.full_name}
                        </EntityLink>
                      </p>
                    )}
                    {contract.company && (
                      <p className="text-xs truncate">
                        <EntityLink type="company" id={contract.company.id} variant="muted">
                          {contract.company.name}
                        </EntityLink>
                      </p>
                    )}
                    {contract.value != null && (
                      <p className="font-medium text-gray-900 dark:text-gray-100">
                        {formatCurrency(contract.value, contract.currency)}
                      </p>
                    )}
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      {contract.end_date ? `Ends ${formatDate(contract.end_date)}` : 'No end date'}
                    </p>
                  </div>
                  <div className="flex gap-4 pt-2 mt-2 border-t border-gray-100 dark:border-gray-700">
                    <Link
                      to={`/contracts/${contract.id}`}
                      className="flex-1 text-center py-2 text-sm font-medium text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-md"
                    >
                      View
                    </Link>
                    <button
                      onClick={() => handleDeleteClick(contract)}
                      className="flex-1 text-center py-2 text-sm font-medium text-red-600 hover:text-red-900 dark:text-red-400 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Desktop table */}
            <div className="hidden md:block overflow-x-auto">
              <table data-list-table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="sticky top-0 z-10 bg-gray-50 dark:bg-gray-900">
                  <tr>
                    <SortableTh field="title" label="Title" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} />
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Contact / Company
                    </th>
                    <SortableTh field="status" label="Status" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} />
                    <SortableTh field="value" label="Value" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} align="right" />
                    <SortableTh field="end_date" label="End Date" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} />
                    <SortableTh field="created_at" label="Created" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} />
                    <th scope="col" className="relative px-6 py-3"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {contracts.map((contract: Contract) => (
                    <tr
                      key={contract.id}
                      role="button"
                      tabIndex={0}
                      className="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
                      onClick={(e) => {
                        if ((e.target as HTMLElement).closest('a, button')) return;
                        if (e.metaKey || e.ctrlKey || e.shiftKey) return;
                        if (window.getSelection()?.toString()) return;
                        navigate(`/contracts/${contract.id}`, {
                          state: { from: window.location.pathname + window.location.search },
                        });
                      }}
                      onKeyDown={(e) => {
                        if (e.target !== e.currentTarget) return;
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          navigate(`/contracts/${contract.id}`, {
                            state: { from: window.location.pathname + window.location.search },
                          });
                        }
                      }}
                    >
                      <td className="px-6 py-4 whitespace-nowrap">
                        <Link
                          to={`/contracts/${contract.id}`}
                          className="text-sm font-medium text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300"
                        >
                          {contract.title}
                        </Link>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        <div>
                          {contract.contact ? (
                            <EntityLink type="contact" id={contract.contact.id} variant="muted">
                              {contract.contact.full_name}
                            </EntityLink>
                          ) : '-'}
                        </div>
                        {contract.company && (
                          <div className="text-xs text-gray-400 dark:text-gray-500">
                            <EntityLink type="company" id={contract.company.id} variant="muted">
                              {contract.company.name}
                            </EntityLink>
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <ContractStatusBadge status={contract.status} />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-right font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {contract.value != null ? formatCurrency(contract.value, contract.currency) : '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {contract.end_date ? formatDate(contract.end_date) : '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(contract.created_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <Link
                          to={`/contracts/${contract.id}`}
                          className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300 mr-4"
                        >
                          View
                        </Link>
                        <button
                          onClick={() => handleDeleteClick(contract)}
                          className="text-red-600 hover:text-red-900 dark:text-red-400 dark:hover:text-red-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 rounded"
                          disabled={deleteContractMutation.isPending}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="bg-white dark:bg-gray-800 px-4 py-3 border-t border-gray-200 dark:border-gray-700 sm:px-6">
              <div className="flex items-center gap-4 mb-2 md:mb-0">
                <select
                  value={pageSize}
                  onChange={(e) => { setPageSize(Number(e.target.value)); setCurrentPage(1); }}
                  aria-label="Results per page"
                  className="text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 px-2 py-1"
                >
                  <option value={10}>10 / page</option>
                  <option value={25}>25 / page</option>
                  <option value={50}>50 / page</option>
                  <option value={100}>100 / page</option>
                </select>
              </div>
              <PaginationBar
                page={currentPage}
                pages={totalPages}
                total={total}
                pageSize={pageSize}
                onPageChange={setCurrentPage}
              />
            </div>
          </>
        )}
      </div>

      {/* Create Modal */}
      <CreateContractModal
        isOpen={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={(id) => {
          setShowCreate(false);
          navigate(`/contracts/${id}`, { state: { from: '/contracts' } });
        }}
      />

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={() => setDeleteConfirm({ isOpen: false, contract: null })}
        onConfirm={handleDeleteConfirm}
        title="Delete Contract"
        message={`Are you sure you want to delete "${deleteConfirm.contract?.title}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteContractMutation.isPending}
      />
    </div>
  );
}

export default ContractsPage;

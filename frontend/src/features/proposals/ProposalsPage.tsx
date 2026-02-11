import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { PlusIcon, SparklesIcon } from '@heroicons/react/24/outline';
import { Button, Modal, ConfirmDialog } from '../../components/ui';
import { SkeletonTable } from '../../components/ui/Skeleton';
import { ProposalForm } from './ProposalForm';
import { AIProposalGenerator } from './AIProposalGenerator';
import { useProposals, useCreateProposal, useDeleteProposal } from '../../hooks/useProposals';
import { formatDate } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { showSuccess, showError } from '../../utils/toast';
import type { Proposal, ProposalCreate } from '../../types';
import clsx from 'clsx';

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'draft', label: 'Draft' },
  { value: 'sent', label: 'Sent' },
  { value: 'viewed', label: 'Viewed' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'rejected', label: 'Rejected' },
];

const STATUS_BADGE_CLASSES: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  sent: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  viewed: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  accepted: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  rejected: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

function ProposalsPage() {
  usePageTitle('Proposals');
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [showAIGenerator, setShowAIGenerator] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; proposal: Proposal | null }>({
    isOpen: false,
    proposal: null,
  });
  const pageSize = 10;

  const {
    data: proposalsData,
    isLoading,
    error,
  } = useProposals({
    page: currentPage,
    page_size: pageSize,
    search: searchQuery || undefined,
    status: statusFilter || undefined,
  });

  const createProposalMutation = useCreateProposal();
  const deleteProposalMutation = useDeleteProposal();

  const proposals = proposalsData?.items ?? [];
  const totalPages = proposalsData?.pages ?? 1;
  const total = proposalsData?.total ?? 0;

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPage(1);
  };

  const handleDeleteClick = (proposal: Proposal) => {
    setDeleteConfirm({ isOpen: true, proposal });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm.proposal) return;
    try {
      await deleteProposalMutation.mutateAsync(deleteConfirm.proposal.id);
      setDeleteConfirm({ isOpen: false, proposal: null });
      showSuccess('Proposal deleted successfully');
    } catch {
      showError('Failed to delete proposal');
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm({ isOpen: false, proposal: null });
  };

  const handleFormSubmit = async (data: ProposalCreate) => {
    try {
      const created = await createProposalMutation.mutateAsync(data);
      setShowForm(false);
      showSuccess('Proposal created successfully');
      navigate(`/proposals/${created.id}`);
    } catch {
      showError('Failed to create proposal');
    }
  };

  const handleFormCancel = () => {
    setShowForm(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Proposals</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Create and manage sales proposals with AI assistance
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <Button
            variant="secondary"
            leftIcon={<SparklesIcon className="h-5 w-5" />}
            onClick={() => setShowAIGenerator(true)}
            className="w-full sm:w-auto"
          >
            AI Generate
          </Button>
          <Button
            leftIcon={<PlusIcon className="h-5 w-5" />}
            onClick={() => setShowForm(true)}
            className="w-full sm:w-auto"
          >
            Create Proposal
          </Button>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 border border-transparent dark:border-gray-700">
        <form onSubmit={handleSearch} className="flex flex-col gap-3 sm:flex-row sm:gap-4">
          <div className="flex-1">
            <label htmlFor="proposal-search" className="sr-only">
              Search proposals
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <svg
                  className="h-5 w-5 text-gray-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
              </div>
              <input
                type="text"
                id="proposal-search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="block w-full pl-10 pr-3 py-2.5 sm:py-2 border border-gray-300 dark:border-gray-600 rounded-md leading-5 bg-white dark:bg-gray-700 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500 focus-visible:border-primary-500 text-base sm:text-sm"
                placeholder="Search by title or proposal number..."
              />
            </div>
          </div>
          <div className="flex gap-3 sm:gap-4">
            <div className="flex-1 sm:flex-none sm:w-48">
              <label htmlFor="proposal-status-filter" className="sr-only">Filter by status</label>
              <select
                id="proposal-status-filter"
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 py-2.5 sm:py-2 text-base sm:text-sm"
              >
                {statusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <Button type="submit" variant="secondary" className="px-4 sm:px-3">
              Search
            </Button>
          </div>
        </form>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
          <p className="text-sm font-medium text-red-800 dark:text-red-300">
            {error instanceof Error ? error.message : 'An error occurred'}
          </p>
        </div>
      )}

      {/* Proposals Table */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
        {isLoading ? (
          <SkeletonTable rows={5} cols={6} />
        ) : proposals.length === 0 ? (
          <div className="text-center py-12 px-4">
            <svg
              className="mx-auto h-12 w-12 text-gray-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No proposals</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Get started by creating a new proposal or using the AI generator.
            </p>
            <div className="mt-6 flex flex-col sm:flex-row gap-3 justify-center">
              <Button
                variant="secondary"
                onClick={() => setShowAIGenerator(true)}
                leftIcon={<SparklesIcon className="h-5 w-5" />}
              >
                AI Generate
              </Button>
              <Button onClick={() => setShowForm(true)}>Create Proposal</Button>
            </div>
          </div>
        ) : (
          <>
            {/* Mobile Card View */}
            <div className="sm:hidden divide-y divide-gray-200 dark:divide-gray-700">
              {proposals.map((proposal: Proposal) => (
                <div key={proposal.id} className="p-4 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <Link
                        to={`/proposals/${proposal.id}`}
                        className="text-sm font-medium text-primary-600 hover:text-primary-900 block truncate"
                      >
                        {proposal.title}
                      </Link>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{proposal.proposal_number}</p>
                    </div>
                    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0', STATUS_BADGE_CLASSES[proposal.status] ?? STATUS_BADGE_CLASSES.draft)}>
                      {proposal.status.charAt(0).toUpperCase() + proposal.status.slice(1)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-500 dark:text-gray-400">
                      {proposal.company?.name ?? proposal.contact?.full_name ?? '-'}
                    </span>
                    <span className="text-gray-500 dark:text-gray-400">{formatDate(proposal.created_at)}</span>
                  </div>
                  <div className="flex gap-4 pt-2 border-t border-gray-100 dark:border-gray-700">
                    <Link
                      to={`/proposals/${proposal.id}`}
                      className="flex-1 text-center py-2 text-sm font-medium text-primary-600 hover:text-primary-900 dark:hover:text-primary-300 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-md transition-colors"
                    >
                      View
                    </Link>
                    <button
                      onClick={() => handleDeleteClick(proposal)}
                      className="flex-1 text-center py-2 text-sm font-medium text-red-600 hover:text-red-900 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
                      disabled={deleteProposalMutation.isPending}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Desktop Table */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-900">
                  <tr>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Proposal
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Contact / Company
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider" style={{ fontVariantNumeric: 'tabular-nums' }}>
                      Views
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Created
                    </th>
                    <th scope="col" className="relative px-6 py-3">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {proposals.map((proposal: Proposal) => (
                    <tr key={proposal.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <Link
                          to={`/proposals/${proposal.id}`}
                          className="text-sm font-medium text-primary-600 hover:text-primary-900"
                        >
                          {proposal.title}
                        </Link>
                        <p className="text-xs text-gray-500 dark:text-gray-400">{proposal.proposal_number}</p>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        <div>{proposal.contact?.full_name ?? '-'}</div>
                        {proposal.company && (
                          <div className="text-xs text-gray-400 dark:text-gray-500">{proposal.company.name}</div>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={clsx('inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium', STATUS_BADGE_CLASSES[proposal.status] ?? STATUS_BADGE_CLASSES.draft)}>
                          {proposal.status.charAt(0).toUpperCase() + proposal.status.slice(1)}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-500 dark:text-gray-400" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {proposal.view_count}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(proposal.created_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <Link
                          to={`/proposals/${proposal.id}`}
                          className="text-primary-600 hover:text-primary-900 mr-4"
                        >
                          View
                        </Link>
                        <button
                          onClick={() => handleDeleteClick(proposal)}
                          className="text-red-600 hover:text-red-900"
                          disabled={deleteProposalMutation.isPending}
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
            <div className="bg-white dark:bg-gray-800 px-4 py-3 flex items-center justify-between border-t border-gray-200 dark:border-gray-700 sm:px-6">
              <div className="flex-1 flex justify-between sm:hidden">
                <Button
                  variant="secondary"
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                >
                  Next
                </Button>
              </div>
              <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
                <p className="text-sm text-gray-700 dark:text-gray-300">
                  Showing{' '}
                  <span className="font-medium">{(currentPage - 1) * pageSize + 1}</span>{' '}
                  to{' '}
                  <span className="font-medium">{Math.min(currentPage * pageSize, total)}</span>{' '}
                  of <span className="font-medium">{total}</span> results
                </p>
                <nav className="relative z-0 inline-flex rounded-md shadow-sm -space-x-px" aria-label="Pagination">
                  <button
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="relative inline-flex items-center px-2 py-2 rounded-l-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span className="sr-only">Previous</span>
                    <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                      <path fillRule="evenodd" d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z" clipRule="evenodd" />
                    </svg>
                  </button>
                  <span className="relative inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm font-medium text-gray-700 dark:text-gray-300">
                    Page {currentPage} of {totalPages}
                  </span>
                  <button
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="relative inline-flex items-center px-2 py-2 rounded-r-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span className="sr-only">Next</span>
                    <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                      <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                    </svg>
                  </button>
                </nav>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Create Form Modal */}
      <Modal
        isOpen={showForm}
        onClose={handleFormCancel}
        title="Create Proposal"
        size="lg"
        fullScreenOnMobile
      >
        <ProposalForm
          onSubmit={handleFormSubmit}
          onCancel={handleFormCancel}
          isLoading={createProposalMutation.isPending}
        />
      </Modal>

      {/* AI Generator Modal */}
      <Modal
        isOpen={showAIGenerator}
        onClose={() => setShowAIGenerator(false)}
        title="Generate Proposal with AI"
        size="md"
      >
        <AIProposalGenerator onClose={() => setShowAIGenerator(false)} />
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete Proposal"
        message={`Are you sure you want to delete "${deleteConfirm.proposal?.title}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteProposalMutation.isPending}
      />
    </div>
  );
}

export default ProposalsPage;

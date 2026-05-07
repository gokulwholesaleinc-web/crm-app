import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { PlusIcon, SparklesIcon, DocumentDuplicateIcon } from '@heroicons/react/24/outline';
import { Button, EntityLink, Modal, ConfirmDialog, StatusBadge, PaginationBar } from '../../components/ui';
import { SkeletonTable } from '../../components/ui/Skeleton';
import { ProposalForm } from './ProposalForm';
import { AIProposalGenerator } from './AIProposalGenerator';
import { TemplateGallery } from './TemplateGallery';
import { SortableTh } from '../../components/shared/SortableTh';
import { useProposals, useCreateProposal, useDeleteProposal } from '../../hooks/useProposals';
import {
  useListPageSizeState,
  useListSortPersistence,
} from '../../hooks/useListPageDefaults';
import { formatDate } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { showSuccess, showError } from '../../utils/toast';
import type { Proposal, ProposalCreate } from '../../types';

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'draft', label: 'Draft' },
  { value: 'sent', label: 'Sent' },
  { value: 'viewed', label: 'Viewed' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'rejected', label: 'Rejected' },
];

type TabType = 'proposals' | 'templates';

function ProposalsPage() {
  usePageTitle('Proposals');
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabType>('proposals');
  const searchQuery = searchParams.get('search') || '';
  // Stale bookmarks with ?status=invalid silently fall back to "All"
  // instead of 422'ing the page on every load.
  const statusParam = searchParams.get('status') || '';
  const statusFilter = statusOptions.some((o) => o.value === statusParam) ? statusParam : '';
  const setSearchQuery = (q: string) =>
    setSearchParams((prev) => { if (q) prev.set('search', q); else prev.delete('search'); return prev; }, { replace: true });
  const setStatusFilter = (s: string) =>
    setSearchParams((prev) => { if (s) prev.set('status', s); else prev.delete('status'); return prev; }, { replace: true });
  const [currentPage, setCurrentPage] = useState(1);
  // Open the create form automatically when arriving with `?action=new`
  // from a contact / company / quote / opportunity detail page. The
  // ProposalForm reads the rest of the query string to prefill the
  // Related Records dropdowns.
  const [showForm, setShowForm] = useState(searchParams.get('action') === 'new');
  const [showAIGenerator, setShowAIGenerator] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; proposal: Proposal | null }>({
    isOpen: false,
    proposal: null,
  });
  const { sortBy, sortDir, toggle: toggleSort } = useListSortPersistence('proposals');
  const [pageSize, setPageSize] = useListPageSizeState('proposals');

  const {
    data: proposalsData,
    isLoading,
    error,
  } = useProposals({
    page: currentPage,
    page_size: pageSize,
    search: searchQuery || undefined,
    status: statusFilter || undefined,
    ...(sortBy && { order_by: sortBy, order_dir: sortDir }),
  });

  // Sorting changes ordering — drop back to page 1.
  const handleSortToggle = (field: string) => {
    setCurrentPage(1);
    toggleSort(field);
  };

  const createProposalMutation = useCreateProposal();
  const deleteProposalMutation = useDeleteProposal();

  const proposals = proposalsData?.items ?? [];
  const totalPages = proposalsData?.pages ?? 1;
  const total = proposalsData?.total ?? 0;

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

      {/* Tab Bar */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="-mb-px flex gap-6" aria-label="Tabs">
          <button
            type="button"
            onClick={() => setActiveTab('proposals')}
            className={`whitespace-nowrap py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
              activeTab === 'proposals'
                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            Proposals
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('templates')}
            className={`whitespace-nowrap py-3 px-1 border-b-2 text-sm font-medium transition-colors inline-flex items-center gap-1.5 ${
              activeTab === 'templates'
                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'
            }`}
          >
            <DocumentDuplicateIcon className="h-4 w-4" aria-hidden="true" />
            Templates
          </button>
        </nav>
      </div>

      {/* Templates Tab */}
      {activeTab === 'templates' && (
        <TemplateGallery
          onProposalCreated={(proposalId) => {
            setActiveTab('proposals');
            navigate(`/proposals/${proposalId}`);
          }}
        />
      )}

      {/* Proposals Tab: Search and Filters */}
      {activeTab === 'proposals' && <>

      {/* Search and Filters */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 border border-transparent dark:border-gray-700">
        <div className="flex flex-col gap-3 sm:flex-row sm:gap-4">
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
                name="search"
                autoComplete="off"
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
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
            <div className="block md:hidden divide-y divide-gray-200 dark:divide-gray-700">
              {proposals.map((proposal: Proposal) => (
                <div key={proposal.id} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700">
                  <div className="flex items-start justify-between gap-2">
                    <Link
                      to={`/proposals/${proposal.id}`}
                      className="flex-1 min-w-0"
                    >
                      <p className="text-sm font-medium text-primary-600 hover:text-primary-900 dark:hover:text-primary-300 truncate">
                        {proposal.title}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{proposal.proposal_number}</p>
                    </Link>
                    <StatusBadge status={proposal.status} size="sm" showDot={false} className="flex-shrink-0" />
                  </div>
                  <div className="mt-2 space-y-1 text-sm text-gray-500 dark:text-gray-400">
                    <p className="truncate">
                      {proposal.contact ? (
                        <EntityLink type="contact" id={proposal.contact.id} variant="muted">
                          {proposal.contact.full_name}
                        </EntityLink>
                      ) : (
                        '-'
                      )}
                    </p>
                    {proposal.company && (
                      <p className="text-xs truncate">
                        <EntityLink type="company" id={proposal.company.id} variant="muted">
                          {proposal.company.name}
                        </EntityLink>
                      </p>
                    )}
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      {formatDate(proposal.created_at)}
                      {proposal.created_by?.full_name && ` · by ${proposal.created_by.full_name}`}
                    </p>
                  </div>
                  <div className="flex gap-4 pt-2 mt-2 border-t border-gray-100 dark:border-gray-700">
                    <Link
                      to={`/proposals/${proposal.id}`}
                      className="flex-1 text-center py-2 text-sm font-medium text-primary-600 hover:text-primary-900 dark:hover:text-primary-300 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-md"
                    >
                      View
                    </Link>
                    <button
                      onClick={() => handleDeleteClick(proposal)}
                      className="flex-1 text-center py-2 text-sm font-medium text-red-600 hover:text-red-900 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                      disabled={deleteProposalMutation.isPending}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Desktop Table */}
            <div className="hidden md:block overflow-x-auto">
              <table data-list-table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="sticky top-0 z-10 bg-gray-50 dark:bg-gray-900">
                  <tr>
                    <SortableTh field="title" label="Proposal" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} />
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Contact / Company
                    </th>
                    <SortableTh field="status" label="Status" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} />
                    <SortableTh field="view_count" label="Views" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} align="right" />
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                      Created by
                    </th>
                    <SortableTh field="created_at" label="Created" sortBy={sortBy} sortDir={sortDir} onToggle={handleSortToggle} />
                    <th scope="col" className="relative px-6 py-3">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {proposals.map((proposal: Proposal) => (
                    <tr
                      key={proposal.id}
                      role="button"
                      tabIndex={0}
                      className="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-500"
                      onClick={(e) => {
                        if ((e.target as HTMLElement).closest('a, button')) return;
                        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
                        if (window.getSelection()?.toString()) return;
                        navigate(`/proposals/${proposal.id}`, {
                          state: { from: window.location.pathname + window.location.search },
                        });
                      }}
                      onKeyDown={(e) => {
                        if (e.target !== e.currentTarget) return;
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          navigate(`/proposals/${proposal.id}`, {
                            state: { from: window.location.pathname + window.location.search },
                          });
                        }
                      }}
                    >
                      <td className="px-6 py-4 whitespace-nowrap">
                        <Link
                          to={`/proposals/${proposal.id}`}
                          className="text-sm font-medium text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300"
                        >
                          {proposal.title}
                        </Link>
                        <p className="text-xs text-gray-500 dark:text-gray-400">{proposal.proposal_number}</p>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        <div>
                          {proposal.contact ? (
                            <EntityLink type="contact" id={proposal.contact.id} variant="muted">
                              {proposal.contact.full_name}
                            </EntityLink>
                          ) : (
                            '-'
                          )}
                        </div>
                        {proposal.company && (
                          <div className="text-xs text-gray-400 dark:text-gray-500">
                            <EntityLink type="company" id={proposal.company.id} variant="muted">
                              {proposal.company.name}
                            </EntityLink>
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <StatusBadge status={proposal.status} size="sm" showDot={false} />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-500 dark:text-gray-400" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {proposal.view_count}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {proposal.created_by?.full_name ?? '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(proposal.created_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <Link
                          to={`/proposals/${proposal.id}`}
                          className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300 mr-4"
                        >
                          View
                        </Link>
                        <button
                          onClick={() => handleDeleteClick(proposal)}
                          className="text-red-600 hover:text-red-900 dark:text-red-400 dark:hover:text-red-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 rounded"
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
            <div className="bg-white dark:bg-gray-800 px-4 py-3 border-t border-gray-200 dark:border-gray-700 sm:px-6">
              <div className="flex items-center gap-4 mb-2 md:mb-0">
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setCurrentPage(1);
                  }}
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

      </>}

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

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { PlusIcon } from '@heroicons/react/24/outline';
import { Button, Modal, ConfirmDialog, StatusBadge, PaginationBar } from '../../components/ui';
import type { StatusType } from '../../components/ui/Badge';
import { SkeletonTable } from '../../components/ui/Skeleton';
import { QuoteForm } from './QuoteForm';
import { useQuotes, useCreateQuote, useDeleteQuote } from '../../hooks/useQuotes';
import { formatCurrency, formatDate } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { showSuccess, showError } from '../../utils/toast';
import type { Quote, QuoteCreate } from '../../types';

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'draft', label: 'Draft' },
  { value: 'sent', label: 'Sent' },
  { value: 'viewed', label: 'Viewed' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'expired', label: 'Expired' },
];

function QuotesPage() {
  usePageTitle('Quotes');
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; quote: Quote | null }>({
    isOpen: false,
    quote: null,
  });
  const pageSize = 10;

  const {
    data: quotesData,
    isLoading,
    error,
  } = useQuotes({
    page: currentPage,
    page_size: pageSize,
    search: searchQuery || undefined,
    status: statusFilter || undefined,
  });

  const createQuoteMutation = useCreateQuote();
  const deleteQuoteMutation = useDeleteQuote();

  const quotes = quotesData?.items ?? [];
  const totalPages = quotesData?.pages ?? 1;
  const total = quotesData?.total ?? 0;

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPage(1);
  };

  const handleDeleteClick = (quote: Quote) => {
    setDeleteConfirm({ isOpen: true, quote });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm.quote) return;
    try {
      await deleteQuoteMutation.mutateAsync(deleteConfirm.quote.id);
      setDeleteConfirm({ isOpen: false, quote: null });
      showSuccess('Quote deleted successfully');
    } catch {
      showError('Failed to delete quote');
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm({ isOpen: false, quote: null });
  };

  const handleFormSubmit = async (data: QuoteCreate) => {
    try {
      const created = await createQuoteMutation.mutateAsync(data);
      setShowForm(false);
      showSuccess('Quote created successfully');
      navigate(`/quotes/${created.id}`);
    } catch {
      showError('Failed to create quote');
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
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Quotes</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Create and manage sales quotes
          </p>
        </div>
        <Button
          leftIcon={<PlusIcon className="h-5 w-5" />}
          onClick={() => setShowForm(true)}
          className="w-full sm:w-auto"
        >
          Create Quote
        </Button>
      </div>

      {/* Search and Filters */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 border border-transparent dark:border-gray-700">
        <form onSubmit={handleSearch} className="flex flex-col gap-3 sm:flex-row sm:gap-4">
          <div className="flex-1">
            <label htmlFor="quote-search" className="sr-only">
              Search quotes
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
                id="quote-search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="block w-full pl-10 pr-3 py-2.5 sm:py-2 border border-gray-300 dark:border-gray-600 rounded-md leading-5 bg-white dark:bg-gray-700 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500 focus-visible:border-primary-500 text-base sm:text-sm"
                placeholder="Search by title or quote number..."
              />
            </div>
          </div>
          <div className="flex gap-3 sm:gap-4">
            <div className="flex-1 sm:flex-none sm:w-48">
              <label htmlFor="quote-status-filter" className="sr-only">Filter by status</label>
              <select
                id="quote-status-filter"
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

      {/* Quotes Table */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
        {isLoading ? (
          <SkeletonTable rows={5} cols={6} />
        ) : quotes.length === 0 ? (
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
            <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No quotes</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Get started by creating a new quote.
            </p>
            <div className="mt-6">
              <Button onClick={() => setShowForm(true)} className="w-full sm:w-auto">Create Quote</Button>
            </div>
          </div>
        ) : (
          <>
            {/* Mobile Card View */}
            <div className="sm:hidden divide-y divide-gray-200 dark:divide-gray-700">
              {quotes.map((quote: Quote) => (
                <div key={quote.id} className="p-4 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <Link
                        to={`/quotes/${quote.id}`}
                        className="text-sm font-medium text-primary-600 hover:text-primary-900 block truncate"
                      >
                        {quote.title}
                      </Link>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{quote.quote_number}</p>
                    </div>
                    <StatusBadge status={quote.status as StatusType} size="sm" showDot={false} className="flex-shrink-0" />
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium text-gray-900 dark:text-gray-100">
                      {formatCurrency(quote.total, quote.currency)}
                    </span>
                    <span className="text-gray-500 dark:text-gray-400">{formatDate(quote.created_at)}</span>
                  </div>
                  <div className="flex gap-4 pt-2 border-t border-gray-100 dark:border-gray-700">
                    <Link
                      to={`/quotes/${quote.id}`}
                      className="flex-1 text-center py-2 text-sm font-medium text-primary-600 hover:text-primary-900 dark:hover:text-primary-300 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-md transition-colors"
                    >
                      View
                    </Link>
                    <button
                      onClick={() => handleDeleteClick(quote)}
                      className="flex-1 text-center py-2 text-sm font-medium text-red-600 hover:text-red-900 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
                      disabled={deleteQuoteMutation.isPending}
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
                      Quote
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Contact / Company
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Total
                    </th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Valid Until
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
                  {quotes.map((quote: Quote) => (
                    <tr key={quote.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <Link
                          to={`/quotes/${quote.id}`}
                          className="text-sm font-medium text-primary-600 hover:text-primary-900"
                        >
                          {quote.title}
                        </Link>
                        <p className="text-xs text-gray-500 dark:text-gray-400">{quote.quote_number}</p>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        <div>{quote.contact?.full_name ?? '-'}</div>
                        {quote.company && (
                          <div className="text-xs text-gray-400 dark:text-gray-500">{quote.company.name}</div>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <StatusBadge status={quote.status as StatusType} size="sm" showDot={false} />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-right font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {formatCurrency(quote.total, quote.currency)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(quote.valid_until)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(quote.created_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <Link
                          to={`/quotes/${quote.id}`}
                          className="text-primary-600 hover:text-primary-900 mr-4"
                        >
                          View
                        </Link>
                        <button
                          onClick={() => handleDeleteClick(quote)}
                          className="text-red-600 hover:text-red-900"
                          disabled={deleteQuoteMutation.isPending}
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
            <PaginationBar
              page={currentPage}
              pages={totalPages}
              total={total}
              pageSize={pageSize}
              onPageChange={setCurrentPage}
            />
          </>
        )}
      </div>

      {/* Create Form Modal */}
      <Modal
        isOpen={showForm}
        onClose={handleFormCancel}
        title="Create Quote"
        size="lg"
        fullScreenOnMobile
      >
        <QuoteForm
          onSubmit={handleFormSubmit}
          onCancel={handleFormCancel}
          isLoading={createQuoteMutation.isPending}
        />
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete Quote"
        message={`Are you sure you want to delete "${deleteConfirm.quote?.title}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteQuoteMutation.isPending}
      />
    </div>
  );
}

export default QuotesPage;

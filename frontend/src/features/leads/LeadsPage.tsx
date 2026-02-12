import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PlusIcon } from '@heroicons/react/24/outline';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Modal, ConfirmDialog } from '../../components/ui';
import { SkeletonTable } from '../../components/ui/Skeleton';
import { LeadForm, LeadFormData } from './components/LeadForm';
import { BulkActionToolbar } from './components/BulkActionToolbar';
import { useLeads, useCreateLead, useUpdateLead, useDeleteLead, leadKeys } from '../../hooks/useLeads';
import { useUsers } from '../../hooks/useAuth';
import { bulkUpdate, bulkAssign } from '../../api/importExport';
import { getStatusBadgeClasses, formatStatusLabel, getScoreColor } from '../../utils';
import { formatDate } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { showSuccess, showError } from '../../utils/toast';
import type { Lead, LeadCreate, LeadUpdate } from '../../types';
import clsx from 'clsx';

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'new', label: 'New' },
  { value: 'contacted', label: 'Contacted' },
  { value: 'qualified', label: 'Qualified' },
  { value: 'unqualified', label: 'Unqualified' },
  { value: 'nurturing', label: 'Nurturing' },
];

function ScoreIndicator({ score }: { score: number }) {
  const percentage = Math.min(100, Math.max(0, score));
  const color = getScoreColor(score);

  return (
    <div className="flex items-center space-x-2">
      <div className="w-16 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div
          className={clsx('h-full rounded-full', {
            'bg-green-500': score >= 80,
            'bg-yellow-500': score >= 60 && score < 80,
            'bg-orange-500': score >= 40 && score < 60,
            'bg-red-500': score < 40,
          })}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className={clsx('text-sm font-medium', color)}>{score}</span>
    </div>
  );
}

function LeadsPage() {
  usePageTitle('Leads');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [editingLead, setEditingLead] = useState<Lead | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; lead: Lead | null }>({
    isOpen: false,
    lead: null,
  });
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const pageSize = 10;

  // Use the hooks for data fetching
  const {
    data: leadsData,
    isLoading,
    error,
  } = useLeads({
    page: currentPage,
    page_size: pageSize,
    search: searchQuery || undefined,
    status: statusFilter || undefined,
  });

  const createLeadMutation = useCreateLead();
  const updateLeadMutation = useUpdateLead();
  const deleteLeadMutation = useDeleteLead();
  const { data: usersData } = useUsers();
  const queryClient = useQueryClient();

  const bulkUpdateMutation = useMutation({
    mutationFn: (updates: Record<string, unknown>) =>
      bulkUpdate({ entity_type: 'leads', entity_ids: selectedIds, updates }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leadKeys.all });
      setSelectedIds([]);
    },
  });

  const bulkAssignMutation = useMutation({
    mutationFn: (ownerId: number) =>
      bulkAssign({ entity_type: 'leads', entity_ids: selectedIds, owner_id: ownerId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: leadKeys.all });
      setSelectedIds([]);
    },
  });

  const leads = leadsData?.items ?? [];
  const totalPages = leadsData?.pages ?? 1;
  const total = leadsData?.total ?? 0;

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPage(1);
  };

  const handleDeleteClick = (lead: Lead) => {
    setDeleteConfirm({ isOpen: true, lead });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm.lead) return;
    try {
      await deleteLeadMutation.mutateAsync(deleteConfirm.lead.id);
      setDeleteConfirm({ isOpen: false, lead: null });
      showSuccess('Lead deleted successfully');
    } catch (err) {
      showError('Failed to delete lead');
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm({ isOpen: false, lead: null });
  };

  const handleEdit = (lead: Lead) => {
    setEditingLead(lead);
    setShowForm(true);
  };

  const handleFormSubmit = async (data: LeadFormData) => {
    try {
      if (editingLead) {
        const updateData: LeadUpdate = {
          first_name: data.firstName,
          last_name: data.lastName,
          email: data.email,
          phone: data.phone,
          company_name: data.company,
          job_title: data.jobTitle,
          status: data.status,
        };
        await updateLeadMutation.mutateAsync({
          id: editingLead.id,
          data: updateData,
        });
        showSuccess('Lead updated successfully');
      } else {
        const createData: LeadCreate = {
          first_name: data.firstName,
          last_name: data.lastName,
          email: data.email,
          phone: data.phone,
          company_name: data.company,
          job_title: data.jobTitle,
          status: data.status,
          budget_currency: 'USD', // Required field
        };
        await createLeadMutation.mutateAsync(createData);
        showSuccess('Lead created successfully');
      }
      setShowForm(false);
      setEditingLead(null);
    } catch (err) {
      showError('Failed to save lead');
    }
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditingLead(null);
  };

  const toggleSelectAll = () => {
    if (selectedIds.length === leads.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(leads.map((l) => l.id));
    }
  };

  const toggleSelectOne = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  const getInitialFormData = (): Partial<LeadFormData> | undefined => {
    if (!editingLead) return undefined;
    return {
      firstName: editingLead.first_name,
      lastName: editingLead.last_name,
      email: editingLead.email || '',
      phone: editingLead.phone || '',
      company: editingLead.company_name || '',
      jobTitle: editingLead.job_title || '',
      source: editingLead.source?.name || 'website',
      status: editingLead.status,
      score: editingLead.score,
    };
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Leads</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Track and manage your sales leads
          </p>
        </div>
        <Button
          leftIcon={<PlusIcon className="h-5 w-5" />}
          onClick={() => setShowForm(true)}
          className="w-full sm:w-auto"
        >
          Add Lead
        </Button>
      </div>

      {/* Search and Filters */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 border border-transparent dark:border-gray-700">
        <form onSubmit={handleSearch} className="flex flex-col gap-3 sm:flex-row sm:gap-4">
          <div className="flex-1">
            <label htmlFor="search" className="sr-only">
              Search leads
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <svg
                  className="h-5 w-5 text-gray-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
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
                type="search"
                name="search"
                id="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="block w-full pl-10 pr-3 py-2.5 sm:py-2 border border-gray-300 dark:border-gray-600 rounded-md leading-5 bg-white dark:bg-gray-700 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus-visible:outline-none focus-visible:placeholder-gray-400 focus-visible:ring-1 focus-visible:ring-primary-500 focus-visible:border-primary-500 text-base sm:text-sm"
                placeholder="Search by name, email, or company..."
              />
            </div>
          </div>
          <div className="flex gap-3 sm:gap-4">
            <div className="flex-1 sm:flex-none sm:w-48">
              <label htmlFor="status-filter" className="sr-only">Filter by status</label>
              <select
                id="status-filter"
                name="status"
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

      {/* Error Message */}
      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
          <div className="flex">
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800 dark:text-red-300">
                {error instanceof Error ? error.message : 'An error occurred'}
              </h3>
            </div>
          </div>
        </div>
      )}

      {/* Delete Error Message */}
      {deleteLeadMutation.isError && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
          <div className="flex">
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800 dark:text-red-300">
                Failed to delete lead
              </h3>
            </div>
          </div>
        </div>
      )}

      {/* Leads Table */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
        {isLoading ? (
          <SkeletonTable rows={5} cols={7} />
        ) : leads.length === 0 ? (
          <div className="text-center py-12 px-4">
            <svg
              className="mx-auto h-12 w-12 text-gray-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
              />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No leads</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Get started by creating a new lead.
            </p>
            <div className="mt-6">
              <Button onClick={() => setShowForm(true)} className="w-full sm:w-auto">Add Lead</Button>
            </div>
          </div>
        ) : (
          <>
            {/* Mobile Card View */}
            <div className="sm:hidden divide-y divide-gray-200 dark:divide-gray-700">
              {leads.map((lead: Lead) => (
                <div key={lead.id} className={clsx('p-4 space-y-3', selectedIds.includes(lead.id) && 'bg-primary-50 dark:bg-primary-900/20')}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start gap-3 min-w-0 flex-1">
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(lead.id)}
                        onChange={() => toggleSelectOne(lead.id)}
                        className="mt-1 rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                      />
                      <div className="min-w-0 flex-1">
                        <Link
                          to={`/leads/${lead.id}`}
                          className="text-sm font-medium text-primary-600 hover:text-primary-900 block truncate"
                        >
                          {lead.first_name} {lead.last_name}
                        </Link>
                        <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{lead.email || '-'}</p>
                        {lead.company_name && (
                          <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{lead.company_name}</p>
                        )}
                      </div>
                    </div>
                    <span className={clsx(getStatusBadgeClasses(lead.status, 'lead'), 'flex-shrink-0')}>
                      {formatStatusLabel(lead.status)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <ScoreIndicator score={lead.score} />
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {lead.source?.name ? formatStatusLabel(lead.source.name) : '-'}
                      </span>
                    </div>
                    <span className="text-xs text-gray-500 dark:text-gray-400">{formatDate(lead.created_at)}</span>
                  </div>
                  <div className="flex gap-4 pt-2 border-t border-gray-100 dark:border-gray-700">
                    <button
                      onClick={() => handleEdit(lead)}
                      className="flex-1 text-center py-2 text-sm font-medium text-primary-600 hover:text-primary-900 dark:hover:text-primary-300 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded-md transition-colors"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDeleteClick(lead)}
                      className="flex-1 text-center py-2 text-sm font-medium text-red-600 hover:text-red-900 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
                      disabled={deleteLeadMutation.isPending}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Desktop Table View */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-900">
                  <tr>
                    <th scope="col" className="px-4 py-3 w-10">
                      <input
                        type="checkbox"
                        checked={leads.length > 0 && selectedIds.length === leads.length}
                        onChange={toggleSelectAll}
                        className="rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                      />
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Name
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Company
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Status
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Score
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Source
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Created
                    </th>
                    <th scope="col" className="relative px-6 py-3">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {leads.map((lead: Lead) => (
                    <tr key={lead.id} className={clsx('hover:bg-gray-50 dark:hover:bg-gray-700', selectedIds.includes(lead.id) && 'bg-primary-50 dark:bg-primary-900/20')}>
                      <td className="px-4 py-4 w-10">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(lead.id)}
                          onChange={() => toggleSelectOne(lead.id)}
                          className="rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                        />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <Link
                          to={`/leads/${lead.id}`}
                          className="text-sm font-medium text-primary-600 hover:text-primary-900"
                        >
                          {lead.first_name} {lead.last_name}
                        </Link>
                        <p className="text-sm text-gray-500 dark:text-gray-400">{lead.email || '-'}</p>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {lead.company_name || '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={getStatusBadgeClasses(lead.status, 'lead')}>
                          {formatStatusLabel(lead.status)}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <ScoreIndicator score={lead.score} />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {lead.source?.name ? formatStatusLabel(lead.source.name) : '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(lead.created_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <button
                          onClick={() => handleEdit(lead)}
                          className="text-primary-600 hover:text-primary-900 mr-4"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDeleteClick(lead)}
                          className="text-red-600 hover:text-red-900"
                          disabled={deleteLeadMutation.isPending}
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
                <div>
                  <p className="text-sm text-gray-700 dark:text-gray-300">
                    Showing{' '}
                    <span className="font-medium">
                      {(currentPage - 1) * pageSize + 1}
                    </span>{' '}
                    to{' '}
                    <span className="font-medium">
                      {Math.min(currentPage * pageSize, total)}
                    </span>{' '}
                    of <span className="font-medium">{total}</span> results
                  </p>
                </div>
                <div>
                  <nav
                    className="relative z-0 inline-flex rounded-md shadow-sm -space-x-px"
                    aria-label="Pagination"
                  >
                    <button
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage === 1}
                      className="relative inline-flex items-center px-2 py-2 rounded-l-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <span className="sr-only">Previous</span>
                      <svg
                        className="h-5 w-5"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fillRule="evenodd"
                          d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    </button>
                    <span className="relative inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm font-medium text-gray-700 dark:text-gray-300">
                      Page {currentPage} of {totalPages}
                    </span>
                    <button
                      onClick={() =>
                        setCurrentPage((p) => Math.min(totalPages, p + 1))
                      }
                      disabled={currentPage === totalPages}
                      className="relative inline-flex items-center px-2 py-2 rounded-r-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <span className="sr-only">Next</span>
                      <svg
                        className="h-5 w-5"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fillRule="evenodd"
                          d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    </button>
                  </nav>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Bulk Action Toolbar */}
      <BulkActionToolbar
        selectedIds={selectedIds}
        entityType="lead(s)"
        onBulkUpdate={async (updates) => { await bulkUpdateMutation.mutateAsync(updates); }}
        onBulkAssign={async (ownerId) => { await bulkAssignMutation.mutateAsync(ownerId); }}
        onClearSelection={() => setSelectedIds([])}
        isLoading={bulkUpdateMutation.isPending || bulkAssignMutation.isPending}
        users={(usersData ?? []).map((u: { id: number; full_name: string }) => ({ id: u.id, full_name: u.full_name }))}
        statusOptions={statusOptions.filter((o) => o.value !== '')}
      />

      {/* Form Modal */}
      <Modal
        isOpen={showForm}
        onClose={handleFormCancel}
        title={editingLead ? 'Edit Lead' : 'Add Lead'}
        size="lg"
        fullScreenOnMobile
      >
        <LeadForm
          initialData={getInitialFormData()}
          onSubmit={handleFormSubmit}
          onCancel={handleFormCancel}
          isLoading={
            createLeadMutation.isPending || updateLeadMutation.isPending
          }
          submitLabel={editingLead ? 'Update Lead' : 'Create Lead'}
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete Lead"
        message={`Are you sure you want to delete ${deleteConfirm.lead?.first_name} ${deleteConfirm.lead?.last_name}? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteLeadMutation.isPending}
      />
    </div>
  );
}

export default LeadsPage;

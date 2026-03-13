/**
 * Companies list page
 */

import { useState, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import {
  PlusIcon,
  FunnelIcon,
  MagnifyingGlassIcon,
  BuildingOffice2Icon,
  GlobeAltIcon,
  UsersIcon,
  PhoneIcon,
  EnvelopeIcon,
} from '@heroicons/react/24/outline';
import { Button, Input, Select, Spinner, Modal, ConfirmDialog, PaginationBar } from '../../components/ui';
import { DuplicateWarningModal } from '../../components/shared/DuplicateWarningModal';
import { CompanyForm } from './components/CompanyForm';
import {
  useCompanies,
  useCreateCompany,
  useUpdateCompany,
  useDeleteCompany,
} from '../../hooks/useCompanies';
import { useCheckDuplicates } from '../../hooks/useDedup';
import { getStatusColor, formatStatusLabel } from '../../utils/statusColors';
import { formatCurrency } from '../../utils/formatters';
import { showSuccess, showError } from '../../utils/toast';
import type { Company, CompanyCreate, CompanyUpdate, CompanyFilters } from '../../types';
import type { DuplicateMatch } from '../../api/dedup';

const statusOptions = [
  { value: '', label: 'All Status' },
  { value: 'prospect', label: 'Prospect' },
  { value: 'customer', label: 'Customer' },
  { value: 'churned', label: 'Churned' },
];

const industryOptions = [
  { value: '', label: 'All Industries' },
  { value: 'technology', label: 'Technology' },
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'finance', label: 'Finance' },
  { value: 'manufacturing', label: 'Manufacturing' },
  { value: 'retail', label: 'Retail' },
  { value: 'education', label: 'Education' },
  { value: 'real_estate', label: 'Real Estate' },
  { value: 'consulting', label: 'Consulting' },
  { value: 'media', label: 'Media & Entertainment' },
  { value: 'other', label: 'Other' },
];

function CompanyCard({
  company,
  onClick,
  onEdit,
  onDelete,
}: {
  company: Company;
  onClick: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const statusStyle = getStatusColor(company.status, 'company');

  return (
    <div
      className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border dark:border-gray-700 p-5 hover:shadow-md transition-shadow cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } }}
    >
      <div className="flex items-start gap-4">
        {/* Logo or Avatar */}
        <div className="flex-shrink-0">
          {company.logo_url ? (
            <img
              src={company.logo_url}
              alt={company.name}
              width={48}
              height={48}
              className="h-12 w-12 rounded-lg object-cover"
            />
          ) : (
            <div className="h-12 w-12 rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
              <BuildingOffice2Icon className="h-6 w-6 text-gray-400" />
            </div>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">{company.name}</h3>
            <div className="flex items-center gap-1 ml-2">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit();
                }}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                aria-label="Edit company"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                  />
                </svg>
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete();
                }}
                className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 hover:text-red-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                aria-label="Delete company"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                  />
                </svg>
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2 mt-1">
            <span
              className={clsx(
                'inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full',
                statusStyle.bg,
                statusStyle.text
              )}
            >
              {formatStatusLabel(company.status)}
            </span>
            {company.industry && (
              <span className="text-xs text-gray-500 dark:text-gray-400 capitalize">{company.industry}</span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-3 text-sm text-gray-500 dark:text-gray-400">
            {company.website && (
              <a
                href={company.website}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="flex items-center gap-1 hover:text-primary-600"
              >
                <GlobeAltIcon className="h-4 w-4 flex-shrink-0" />
                <span className="truncate max-w-[150px]">
                  {company.website.replace(/^https?:\/\//, '')}
                </span>
              </a>
            )}
            {company.email && (
              <a
                href={`mailto:${company.email}`}
                onClick={(e) => e.stopPropagation()}
                className="flex items-center gap-1 hover:text-primary-600"
              >
                <EnvelopeIcon className="h-4 w-4 flex-shrink-0" />
                <span className="truncate max-w-[180px]">{company.email}</span>
              </a>
            )}
            {company.phone && (
              <a
                href={`tel:${company.phone}`}
                onClick={(e) => e.stopPropagation()}
                className="flex items-center gap-1 hover:text-primary-600"
              >
                <PhoneIcon className="h-4 w-4 flex-shrink-0" />
                <span>{company.phone}</span>
              </a>
            )}
            <span className="flex items-center gap-1">
              <UsersIcon className="h-4 w-4 flex-shrink-0" />
              {company.contact_count} contacts
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-xs text-gray-500 dark:text-gray-400">
            {(company.city || company.state || company.country) && (
              <span>{[company.city, company.state, company.country].filter(Boolean).join(', ')}</span>
            )}
            {company.employee_count != null ? (
              <span>{company.employee_count} employees</span>
            ) : company.company_size ? (
              <span>Size: {company.company_size}</span>
            ) : null}
            {company.link_creative_tier && (
              <span>Tier {company.link_creative_tier}</span>
            )}
            {company.account_manager && (
              <span>AM: {company.account_manager}</span>
            )}
            {company.annual_revenue != null && (
              <span>Revenue: {formatCurrency(company.annual_revenue)}</span>
            )}
            {company.sow_url && (
              <a
                href={company.sow_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="hover:text-primary-600"
              >
                SOW
              </a>
            )}
          </div>

          {company.description && (
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
              {company.description}
            </p>
          )}

          {company.tags && company.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-3">
              {company.tags.slice(0, 3).map((tag) => (
                <span
                  key={tag.id}
                  className="text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
                  style={tag.color ? { backgroundColor: `${tag.color}20`, color: tag.color } : undefined}
                >
                  {tag.name}
                </span>
              ))}
              {company.tags.length > 3 && (
                <span className="text-xs text-gray-500">+{company.tags.length - 3} more</span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function CompaniesPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showFilters, setShowFilters] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingCompany, setEditingCompany] = useState<Company | null>(null);
  const [searchQuery, setSearchQuery] = useState(searchParams.get('search') || '');
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; company: Company | null }>({
    isOpen: false,
    company: null,
  });
  const [pendingFormData, setPendingFormData] = useState<CompanyCreate | CompanyUpdate | null>(null);
  const [duplicateResults, setDuplicateResults] = useState<DuplicateMatch[]>([]);
  const [showDuplicateWarning, setShowDuplicateWarning] = useState(false);

  // Get filter values from URL params
  const filters: CompanyFilters = useMemo(
    () => ({
      page: parseInt(searchParams.get('page') || '1', 10),
      page_size: parseInt(searchParams.get('page_size') || '12', 10),
      search: searchParams.get('search') || undefined,
      status: searchParams.get('status') || undefined,
      industry: searchParams.get('industry') || undefined,
    }),
    [searchParams]
  );

  // Fetch companies
  const { data: companiesData, isLoading } = useCompanies(filters);

  // Mutations
  const createCompany = useCreateCompany();
  const updateCompany = useUpdateCompany();
  const deleteCompany = useDeleteCompany();
  const checkDuplicatesMutation = useCheckDuplicates();

  const updateFilter = (key: string, value: string) => {
    const newParams = new URLSearchParams(searchParams);
    if (value) {
      newParams.set(key, value);
    } else {
      newParams.delete(key);
    }
    if (key !== 'page') {
      newParams.set('page', '1');
    }
    setSearchParams(newParams);
  };

  const handleDeleteClick = (company: Company) => {
    setDeleteConfirm({ isOpen: true, company });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm.company) return;
    try {
      await deleteCompany.mutateAsync(deleteConfirm.company.id);
      setDeleteConfirm({ isOpen: false, company: null });
      showSuccess('Company deleted successfully');
    } catch {
      showError('Failed to delete company');
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm({ isOpen: false, company: null });
  };

  const handleEdit = (company: Company) => {
    setEditingCompany(company);
    setShowForm(true);
  };

  const doCreateCompany = async (data: CompanyCreate) => {
    await createCompany.mutateAsync(data);
    showSuccess('Company created successfully');
    setShowForm(false);
    setEditingCompany(null);
    setPendingFormData(null);
  };

  const handleFormSubmit = async (data: CompanyCreate | CompanyUpdate) => {
    try {
      if (editingCompany) {
        await updateCompany.mutateAsync({ id: editingCompany.id, data: data as CompanyUpdate });
        showSuccess('Company updated successfully');
        setShowForm(false);
        setEditingCompany(null);
      } else {
        // Check for duplicates before creating
        const result = await checkDuplicatesMutation.mutateAsync({
          entityType: 'companies',
          data: { name: (data as CompanyCreate).name },
        });
        if (result.has_duplicates) {
          setPendingFormData(data as CompanyCreate);
          setDuplicateResults(result.duplicates);
          setShowDuplicateWarning(true);
          return;
        }
        await doCreateCompany(data as CompanyCreate);
      }
    } catch {
      showError('Failed to save company');
    }
  };

  const handleCreateAnyway = async () => {
    if (!pendingFormData) return;
    setShowDuplicateWarning(false);
    try {
      await doCreateCompany(pendingFormData as CompanyCreate);
    } catch {
      showError('Failed to create company');
    }
  };

  const handleViewDuplicate = (id: number) => {
    setShowDuplicateWarning(false);
    setShowForm(false);
    setPendingFormData(null);
    navigate(`/companies/${id}`);
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditingCompany(null);
  };

  const companies = companiesData?.items || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Companies</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Manage your accounts and track business relationships
          </p>
        </div>
        <Button
          leftIcon={<PlusIcon className="h-5 w-5" />}
          onClick={() => setShowForm(true)}
          className="w-full sm:w-auto"
        >
          Add Company
        </Button>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
        <div className="flex-1 sm:max-w-md">
          <Input
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              updateFilter('search', e.target.value);
            }}
            placeholder="Search companies..."
            leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
            aria-label="Search companies"
            name="search"
          />
        </div>
        <div className="flex items-center justify-between gap-3 sm:gap-4">
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<FunnelIcon className="h-4 w-4" />}
            onClick={() => setShowFilters(!showFilters)}
          >
            Filters
          </Button>

          {companiesData && (
            <div className="text-sm text-gray-500 dark:text-gray-400">
              {companies.length} of {companiesData.total}
            </div>
          )}
        </div>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
            <Select
              label="Status"
              options={statusOptions}
              value={filters.status || ''}
              onChange={(e) => updateFilter('status', e.target.value)}
            />
            <Select
              label="Industry"
              options={industryOptions}
              value={filters.industry || ''}
              onChange={(e) => updateFilter('industry', e.target.value)}
            />
          </div>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : companies.length === 0 ? (
        <div className="text-center py-12 px-4">
          <BuildingOffice2Icon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No companies</h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Get started by adding a new company.
          </p>
          <div className="mt-6">
            <Button onClick={() => setShowForm(true)} className="w-full sm:w-auto">
              <PlusIcon className="h-5 w-5 mr-2" />
              Add Company
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {companies.map((company) => (
              <CompanyCard
                key={company.id}
                company={company}
                onClick={() => navigate(`/companies/${company.id}`)}
                onEdit={() => handleEdit(company)}
                onDelete={() => handleDeleteClick(company)}
              />
            ))}
          </div>

          {/* Pagination */}
          {companiesData && (
            <div className="flex flex-col gap-3 pt-4 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
              <div className="flex items-center justify-center gap-3 sm:justify-start">
                <span className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
                  {companiesData.total} total
                </span>
                <select
                  value={filters.page_size}
                  onChange={(e) => updateFilter('page_size', e.target.value)}
                  aria-label="Results per page"
                  className="text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 px-2 py-1"
                >
                  <option value={12}>12 / page</option>
                  <option value={25}>25 / page</option>
                  <option value={50}>50 / page</option>
                  <option value={100}>100 / page</option>
                </select>
              </div>
              <PaginationBar
                page={filters.page ?? 1}
                pages={companiesData.pages}
                total={companiesData.total}
                pageSize={filters.page_size ?? 12}
                onPageChange={(p) => updateFilter('page', String(p))}
              />
            </div>
          )}
        </>
      )}

      {/* Form Modal */}
      <Modal
        isOpen={showForm}
        onClose={handleFormCancel}
        title={editingCompany ? 'Edit Company' : 'Add Company'}
        size="lg"
      >
        <CompanyForm
          company={editingCompany || undefined}
          onSubmit={handleFormSubmit}
          onCancel={handleFormCancel}
          isLoading={createCompany.isPending || updateCompany.isPending || checkDuplicatesMutation.isPending}
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete Company"
        message={`Are you sure you want to delete ${deleteConfirm.company?.name}? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteCompany.isPending}
      />

      {/* Duplicate Warning Modal */}
      <DuplicateWarningModal
        isOpen={showDuplicateWarning}
        onClose={() => { setShowDuplicateWarning(false); setPendingFormData(null); }}
        onCreateAnyway={handleCreateAnyway}
        onViewDuplicate={handleViewDuplicate}
        duplicates={duplicateResults}
        entityType="companies"
      />
    </div>
  );
}

export default CompaniesPage;

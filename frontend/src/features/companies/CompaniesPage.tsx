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
} from '@heroicons/react/24/outline';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Spinner } from '../../components/ui/Spinner';
import { CompanyForm } from './components/CompanyForm';
import {
  useCompanies,
  useCreateCompany,
  useUpdateCompany,
  useDeleteCompany,
} from '../../hooks/useCompanies';
import type { Company, CompanyCreate, CompanyUpdate, CompanyFilters } from '../../types';

const defaultCompanyStatusColor = { bg: 'bg-blue-100', text: 'text-blue-700', dot: 'bg-blue-400' };

const statusColors: Record<string, { bg: string; text: string; dot: string }> = {
  prospect: defaultCompanyStatusColor,
  customer: { bg: 'bg-green-100', text: 'text-green-700', dot: 'bg-green-400' },
  churned: { bg: 'bg-gray-100', text: 'text-gray-700', dot: 'bg-gray-400' },
};

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

function formatCurrency(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
    notation: 'compact',
  }).format(amount);
}

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
  const statusStyle = statusColors[company.status] ?? defaultCompanyStatusColor;

  return (
    <div
      className="bg-white rounded-lg shadow-sm border p-5 hover:shadow-md transition-all cursor-pointer"
      onClick={onClick}
    >
      <div className="flex items-start gap-4">
        {/* Logo or Avatar */}
        <div className="flex-shrink-0">
          {company.logo_url ? (
            <img
              src={company.logo_url}
              alt={company.name}
              className="h-12 w-12 rounded-lg object-cover"
            />
          ) : (
            <div className="h-12 w-12 rounded-lg bg-gray-100 flex items-center justify-center">
              <BuildingOffice2Icon className="h-6 w-6 text-gray-400" />
            </div>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-gray-900 truncate">{company.name}</h3>
            <div className="flex items-center gap-1 ml-2">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit();
                }}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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
                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-red-500"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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
              <span className={clsx('h-1.5 w-1.5 rounded-full', statusStyle.dot)} />
              {company.status.charAt(0).toUpperCase() + company.status.slice(1)}
            </span>
            {company.industry && (
              <span className="text-xs text-gray-500 capitalize">{company.industry}</span>
            )}
          </div>

          <div className="flex items-center gap-4 mt-3 text-sm text-gray-500">
            {company.website && (
              <a
                href={company.website}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="flex items-center gap-1 hover:text-primary-600"
              >
                <GlobeAltIcon className="h-4 w-4" />
                <span className="truncate max-w-[150px]">
                  {company.website.replace(/^https?:\/\//, '')}
                </span>
              </a>
            )}
            <span className="flex items-center gap-1">
              <UsersIcon className="h-4 w-4" />
              {company.contact_count} contacts
            </span>
          </div>

          <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
            {company.city && company.country && (
              <span>
                {company.city}, {company.country}
              </span>
            )}
            {company.annual_revenue && (
              <span>Revenue: {formatCurrency(company.annual_revenue)}</span>
            )}
          </div>

          {company.tags && company.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-3">
              {company.tags.slice(0, 3).map((tag) => (
                <span
                  key={tag.id}
                  className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600"
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

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    updateFilter('search', searchQuery);
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this company?')) return;
    try {
      await deleteCompany.mutateAsync(id);
    } catch (error) {
      console.error('Failed to delete company:', error);
    }
  };

  const handleEdit = (company: Company) => {
    setEditingCompany(company);
    setShowForm(true);
  };

  const handleFormSubmit = async (data: CompanyCreate | CompanyUpdate) => {
    try {
      if (editingCompany) {
        await updateCompany.mutateAsync({ id: editingCompany.id, data: data as CompanyUpdate });
      } else {
        await createCompany.mutateAsync(data as CompanyCreate);
      }
      setShowForm(false);
      setEditingCompany(null);
    } catch (error) {
      console.error('Failed to save company:', error);
    }
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditingCompany(null);
  };

  const companies = companiesData?.items || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Companies</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage your accounts and track business relationships
          </p>
        </div>
        <Button leftIcon={<PlusIcon className="h-5 w-5" />} onClick={() => setShowForm(true)}>
          Add Company
        </Button>
      </div>

      {/* Search and Filters */}
      <div className="flex items-center gap-4 flex-wrap">
        <form onSubmit={handleSearch} className="flex-1 max-w-md">
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search companies..."
            leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
          />
        </form>
        <Button
          variant="ghost"
          size="sm"
          leftIcon={<FunnelIcon className="h-4 w-4" />}
          onClick={() => setShowFilters(!showFilters)}
        >
          Filters
        </Button>

        {companiesData && (
          <div className="text-sm text-gray-500">
            Showing {companies.length} of {companiesData.total} companies
          </div>
        )}
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="bg-gray-50 rounded-lg p-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
        <div className="text-center py-12">
          <BuildingOffice2Icon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">No companies</h3>
          <p className="mt-1 text-sm text-gray-500">
            Get started by adding a new company.
          </p>
          <div className="mt-6">
            <Button onClick={() => setShowForm(true)}>
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
                onDelete={() => handleDelete(company.id)}
              />
            ))}
          </div>

          {/* Pagination */}
          {companiesData && companiesData.pages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-4">
              <Button
                variant="secondary"
                size="sm"
                disabled={filters.page === 1}
                onClick={() => updateFilter('page', String((filters.page || 1) - 1))}
              >
                Previous
              </Button>
              <span className="text-sm text-gray-600">
                Page {filters.page} of {companiesData.pages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={filters.page === companiesData.pages}
                onClick={() => updateFilter('page', String((filters.page || 1) + 1))}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}

      {/* Form Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-screen items-center justify-center p-4">
            <div
              className="fixed inset-0 bg-black bg-opacity-25"
              onClick={handleFormCancel}
            />
            <div className="relative bg-white rounded-lg shadow-xl max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                {editingCompany ? 'Edit Company' : 'Add Company'}
              </h2>
              <CompanyForm
                company={editingCompany || undefined}
                onSubmit={handleFormSubmit}
                onCancel={handleFormCancel}
                isLoading={createCompany.isPending || updateCompany.isPending}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CompaniesPage;

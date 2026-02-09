/**
 * Company detail page with contacts list, activities, and notes tabs
 */

import { useState, lazy, Suspense } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import clsx from 'clsx';
import {
  ArrowLeftIcon,
  BuildingOffice2Icon,
  GlobeAltIcon,
  EnvelopeIcon,
  PhoneIcon,
  MapPinIcon,
  UsersIcon,
  LinkIcon,
} from '@heroicons/react/24/outline';
import { Button, Spinner, Modal, ConfirmDialog } from '../../components/ui';

const NotesList = lazy(() => import('../../components/shared/NotesList'));
const AttachmentList = lazy(() => import('../../components/shared/AttachmentList'));
const AuditTimeline = lazy(() => import('../../components/shared/AuditTimeline'));
const CommentSection = lazy(() => import('../../components/shared/CommentSection'));
import { CompanyForm } from './components/CompanyForm';
import { useCompany, useUpdateCompany, useDeleteCompany } from '../../hooks/useCompanies';
import { useContacts } from '../../hooks/useContacts';
import { useTimeline } from '../../hooks/useActivities';
import { getStatusColor, formatStatusLabel } from '../../utils/statusColors';
import { formatCurrency, formatDate } from '../../utils/formatters';
import type { CompanyUpdate, Contact } from '../../types';

type TabType = 'overview' | 'activities' | 'notes' | 'attachments' | 'comments' | 'history';

function DetailItem({
  icon: Icon,
  label,
  value,
  link,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | null | undefined;
  link?: string;
}) {
  if (!value) return null;

  const content = (
    <div className="flex items-start gap-3 py-2">
      <Icon className="h-5 w-5 text-gray-400 mt-0.5" />
      <div>
        <p className="text-xs text-gray-500">{label}</p>
        <p className={clsx('text-sm text-gray-900', link && 'hover:text-primary-600')}>{value}</p>
      </div>
    </div>
  );

  if (link) {
    return (
      <a href={link} target="_blank" rel="noopener noreferrer">
        {content}
      </a>
    );
  }

  return content;
}

function ContactRow({ contact }: { contact: Contact }) {
  return (
    <Link
      to={`/contacts/${contact.id}`}
      className="flex flex-col gap-2 p-3 rounded-lg hover:bg-gray-50 transition-colors sm:flex-row sm:items-center sm:gap-4"
    >
      <div className="flex items-center gap-3 sm:gap-4">
        {contact.avatar_url ? (
          <img
            src={contact.avatar_url}
            alt={contact.full_name}
            className="h-10 w-10 rounded-full object-cover flex-shrink-0"
          />
        ) : (
          <div className="h-10 w-10 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0">
            <span className="text-sm font-medium text-gray-600">
              {contact.first_name[0]}
              {contact.last_name[0]}
            </span>
          </div>
        )}
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate">{contact.full_name}</p>
          <p className="text-xs text-gray-500 truncate">
            {contact.job_title || 'No title'}
            {contact.department && ` - ${contact.department}`}
          </p>
        </div>
      </div>
      <div className="text-xs text-gray-500 pl-13 sm:pl-0 sm:ml-auto sm:text-right">
        {contact.email && (
          <p className="truncate">{contact.email}</p>
        )}
        {contact.phone && <p>{contact.phone}</p>}
      </div>
    </Link>
  );
}

export function CompanyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const companyId = id ? parseInt(id, 10) : undefined;

  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Fetch company data
  const { data: company, isLoading: isLoadingCompany } = useCompany(companyId);

  // Fetch contacts for this company
  const { data: contactsData, isLoading: isLoadingContacts } = useContacts({
    company_id: companyId,
    page_size: 50,
  });

  // Fetch timeline/activities - only when on activities tab
  const shouldFetchActivities = activeTab === 'activities' && !!companyId;
  const { data: timelineData, isLoading: isLoadingActivities } = useTimeline(
    shouldFetchActivities ? 'company' : '',
    shouldFetchActivities ? companyId! : 0
  );

  const activities = timelineData?.items || [];

  // Mutations
  const updateCompany = useUpdateCompany();
  const deleteCompany = useDeleteCompany();

  const handleDeleteConfirm = async () => {
    if (!companyId) return;
    try {
      await deleteCompany.mutateAsync(companyId);
      navigate('/companies');
    } catch (error) {
      console.error('Failed to delete company:', error);
    }
  };

  const handleFormSubmit = async (data: CompanyUpdate) => {
    if (!companyId) return;
    try {
      await updateCompany.mutateAsync({ id: companyId, data });
      setShowEditForm(false);
    } catch (error) {
      console.error('Failed to update company:', error);
    }
  };

  if (isLoadingCompany) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!company) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500">Company not found</p>
        <Button variant="secondary" className="mt-4" onClick={() => navigate('/companies')}>
          Back to Companies
        </Button>
      </div>
    );
  }

  const statusStyle = getStatusColor(company.status, 'company');
  const contacts = contactsData?.items || [];

  const fullAddress = [
    company.address_line1,
    company.address_line2,
    [company.city, company.state].filter(Boolean).join(', '),
    company.postal_code,
    company.country,
  ]
    .filter(Boolean)
    .join('\n');

  const tabs: { id: TabType; name: string }[] = [
    { id: 'overview', name: 'Overview' },
    { id: 'activities', name: 'Activities' },
    { id: 'notes', name: 'Notes' },
    { id: 'attachments', name: 'Attachments' },
    { id: 'comments', name: 'Comments' },
    { id: 'history', name: 'History' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4">
        <div className="flex items-start gap-3 sm:gap-4">
          <button
            onClick={() => navigate('/companies')}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors flex-shrink-0"
          >
            <ArrowLeftIcon className="h-5 w-5 text-gray-500" />
          </button>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4 flex-1 min-w-0">
            {company.logo_url ? (
              <img
                src={company.logo_url}
                alt={company.name}
                className="h-12 w-12 sm:h-16 sm:w-16 rounded-lg object-cover flex-shrink-0"
              />
            ) : (
              <div className="h-12 w-12 sm:h-16 sm:w-16 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
                <BuildingOffice2Icon className="h-6 w-6 sm:h-8 sm:w-8 text-gray-400" />
              </div>
            )}
            <div className="min-w-0">
              <h1 className="text-xl sm:text-2xl font-bold text-gray-900 truncate">{company.name}</h1>
              <div className="flex flex-wrap items-center gap-2 sm:gap-3 mt-1">
                <span
                  className={clsx(
                    'inline-flex items-center gap-1 text-sm font-medium px-2.5 py-0.5 rounded-full',
                    statusStyle.bg,
                    statusStyle.text
                  )}
                >
                  {formatStatusLabel(company.status)}
                </span>
                {company.industry && (
                  <span className="text-sm text-gray-500 capitalize">{company.industry}</span>
                )}
              </div>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto sm:ml-auto">
          <Button variant="secondary" onClick={() => setShowEditForm(true)} className="flex-1 sm:flex-none">
            Edit
          </Button>
          <Button variant="danger" onClick={() => setShowDeleteConfirm(true)} className="flex-1 sm:flex-none">
            Delete
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 overflow-x-auto">
        <nav className="-mb-px flex space-x-4 sm:space-x-8 min-w-max px-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex-shrink-0',
                activeTab === tab.id
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              )}
            >
              {tab.name}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Main Info */}
          <div className="space-y-6 lg:col-span-2">
            {/* Description */}
            {company.description && (
              <div className="bg-white rounded-lg shadow-sm border p-6">
                <h3 className="text-sm font-medium text-gray-900 mb-2">About</h3>
                <p className="text-sm text-gray-600 whitespace-pre-wrap">{company.description}</p>
              </div>
            )}

            {/* Contacts */}
            <div className="bg-white rounded-lg shadow-sm border">
              <div className="px-4 py-4 border-b flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
                <h3 className="text-lg font-semibold text-gray-900">
                  Contacts ({contacts.length})
                </h3>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => navigate(`/contacts?company_id=${companyId}&action=new`)}
                  className="w-full sm:w-auto"
                >
                  Add Contact
                </Button>
              </div>
              {isLoadingContacts ? (
                <div className="flex items-center justify-center py-8">
                  <Spinner />
                </div>
              ) : contacts.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <UsersIcon className="mx-auto h-8 w-8 text-gray-400 mb-2" />
                  <p>No contacts associated with this company</p>
                </div>
              ) : (
                <div className="divide-y">
                  {contacts.map((contact) => (
                    <ContactRow key={contact.id} contact={contact} />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Contact Info */}
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <h3 className="text-sm font-medium text-gray-900 mb-4">Contact Information</h3>
              <div className="space-y-1">
                <DetailItem
                  icon={GlobeAltIcon}
                  label="Website"
                  value={company.website?.replace(/^https?:\/\//, '')}
                  link={company.website || undefined}
                />
                <DetailItem
                  icon={EnvelopeIcon}
                  label="Email"
                  value={company.email}
                  link={company.email ? `mailto:${company.email}` : undefined}
                />
                <DetailItem
                  icon={PhoneIcon}
                  label="Phone"
                  value={company.phone}
                  link={company.phone ? `tel:${company.phone}` : undefined}
                />
                {fullAddress && (
                  <DetailItem icon={MapPinIcon} label="Address" value={fullAddress} />
                )}
              </div>
            </div>

            {/* Business Info */}
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <h3 className="text-sm font-medium text-gray-900 mb-4">Business Details</h3>
              <div className="space-y-3">
                {company.annual_revenue && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500">Annual Revenue</span>
                    <span className="text-sm font-medium text-gray-900">
                      {formatCurrency(company.annual_revenue)}
                    </span>
                  </div>
                )}
                {company.employee_count && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500">Employees</span>
                    <span className="text-sm font-medium text-gray-900">
                      {company.employee_count.toLocaleString()}
                    </span>
                  </div>
                )}
                {company.company_size && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500">Company Size</span>
                    <span className="text-sm font-medium text-gray-900">{company.company_size}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Social Links */}
            {(company.linkedin_url || company.twitter_handle) && (
              <div className="bg-white rounded-lg shadow-sm border p-6">
                <h3 className="text-sm font-medium text-gray-900 mb-4">Social Links</h3>
                <div className="space-y-2">
                  {company.linkedin_url && (
                    <a
                      href={company.linkedin_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 text-sm text-gray-600 hover:text-primary-600"
                    >
                      <LinkIcon className="h-4 w-4" />
                      LinkedIn
                    </a>
                  )}
                  {company.twitter_handle && (
                    <a
                      href={`https://twitter.com/${company.twitter_handle.replace('@', '')}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 text-sm text-gray-600 hover:text-primary-600"
                    >
                      <LinkIcon className="h-4 w-4" />
                      {company.twitter_handle}
                    </a>
                  )}
                </div>
              </div>
            )}

            {/* Tags */}
            {company.tags && company.tags.length > 0 && (
              <div className="bg-white rounded-lg shadow-sm border p-6">
                <h3 className="text-sm font-medium text-gray-900 mb-4">Tags</h3>
                <div className="flex flex-wrap gap-2">
                  {company.tags.map((tag) => (
                    <span
                      key={tag.id}
                      className="text-xs px-2.5 py-1 rounded-full bg-gray-100 text-gray-600"
                      style={
                        tag.color ? { backgroundColor: `${tag.color}20`, color: tag.color } : undefined
                      }
                    >
                      {tag.name}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Timestamps */}
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <h3 className="text-sm font-medium text-gray-900 mb-4">Record Info</h3>
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Created</span>
                  <span className="text-gray-900">{formatDate(company.created_at, 'long')}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-gray-500">Last Updated</span>
                  <span className="text-gray-900">{formatDate(company.updated_at, 'long')}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'activities' && (
        <div className="bg-white shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            {isLoadingActivities ? (
              <div className="flex items-center justify-center py-4">
                <Spinner />
              </div>
            ) : activities.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">
                No activities recorded yet.
              </p>
            ) : (
              <ul className="space-y-4">
                {activities.map((activity) => (
                  <li
                    key={activity.id}
                    className="flex items-start space-x-3 pb-4 border-b border-gray-100 last:border-0"
                  >
                    <div className="flex-shrink-0">
                      <div className="h-8 w-8 rounded-full bg-primary-100 flex items-center justify-center">
                        <svg
                          className="h-4 w-4 text-primary-600"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                          />
                        </svg>
                      </div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-900">
                        {activity.subject}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {formatDate(activity.created_at)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {activeTab === 'notes' && companyId && (
        <Suspense fallback={<div className="bg-white shadow rounded-lg p-6 animate-pulse"><div className="h-4 bg-gray-200 rounded w-1/3 mb-4" /><div className="space-y-3"><div className="h-3 bg-gray-200 rounded" /><div className="h-3 bg-gray-200 rounded w-5/6" /></div></div>}>
          <NotesList entityType="company" entityId={companyId} />
        </Suspense>
      )}

      {activeTab === 'attachments' && companyId && (
        <Suspense fallback={<div className="bg-white shadow rounded-lg p-6 animate-pulse"><div className="h-4 bg-gray-200 rounded w-1/3 mb-4" /><div className="space-y-3"><div className="h-3 bg-gray-200 rounded" /><div className="h-3 bg-gray-200 rounded w-5/6" /></div></div>}>
          <AttachmentList entityType="companies" entityId={companyId} />
        </Suspense>
      )}

      {/* Comments Tab */}
      {activeTab === 'comments' && companyId && (
        <Suspense fallback={<div className="bg-white shadow rounded-lg p-6 animate-pulse"><div className="h-4 bg-gray-200 rounded w-1/3 mb-4" /><div className="space-y-3"><div className="h-3 bg-gray-200 rounded" /><div className="h-3 bg-gray-200 rounded w-5/6" /></div></div>}>
          <CommentSection entityType="companies" entityId={companyId} />
        </Suspense>
      )}

      {/* History Tab */}
      {activeTab === 'history' && companyId && (
        <Suspense fallback={<div className="bg-white shadow rounded-lg p-6 animate-pulse"><div className="h-4 bg-gray-200 rounded w-1/3 mb-4" /><div className="space-y-3"><div className="h-3 bg-gray-200 rounded" /><div className="h-3 bg-gray-200 rounded w-5/6" /></div></div>}>
          <AuditTimeline entityType="companies" entityId={companyId} />
        </Suspense>
      )}

      {/* Edit Form Modal */}
      <Modal
        isOpen={showEditForm}
        onClose={() => setShowEditForm(false)}
        title="Edit Company"
        size="lg"
      >
        <CompanyForm
          company={company}
          onSubmit={handleFormSubmit}
          onCancel={() => setShowEditForm(false)}
          isLoading={updateCompany.isPending}
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDeleteConfirm}
        title="Delete Company"
        message={`Are you sure you want to delete ${company.name}? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteCompany.isPending}
      />
    </div>
  );
}

export default CompanyDetailPage;

import { useState, lazy, Suspense } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Button, Spinner, Modal, ConfirmDialog } from '../../components/ui';

const NotesList = lazy(() => import('../../components/shared/NotesList'));
const AttachmentList = lazy(() => import('../../components/shared/AttachmentList'));
const AuditTimeline = lazy(() => import('../../components/shared/AuditTimeline'));
const CommentSection = lazy(() => import('../../components/shared/CommentSection'));
import { OpportunityForm, OpportunityFormData } from './components/OpportunityForm';
import { AIInsightsCard, NextBestActionCard } from '../../components/ai';
import { useOpportunity, useDeleteOpportunity, useUpdateOpportunity, usePipelineStages } from '../../hooks/useOpportunities';
import { useContacts } from '../../hooks/useContacts';
import { useCompanies } from '../../hooks/useCompanies';
import { useTimeline } from '../../hooks/useActivities';
import { formatCurrency, formatDate, formatPercentage } from '../../utils/formatters';
import { getStatusBadgeClasses } from '../../utils';
import type { OpportunityUpdate } from '../../types';
import clsx from 'clsx';

type TabType = 'details' | 'activities' | 'notes' | 'attachments' | 'comments' | 'history';

function OpportunityDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const opportunityId = id ? parseInt(id, 10) : undefined;
  const [activeTab, setActiveTab] = useState<TabType>('details');
  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Data fetching
  const { data: opportunity, isLoading, error } = useOpportunity(opportunityId);
  const deleteOpportunityMutation = useDeleteOpportunity();
  const updateOpportunityMutation = useUpdateOpportunity();
  const { data: pipelineStages } = usePipelineStages();
  const { data: contactsData } = useContacts({ page_size: 100 });
  const { data: companiesData } = useCompanies({ page_size: 100 });

  // Fetch timeline/activities - only when on activities tab
  const shouldFetchActivities = activeTab === 'activities' && !!opportunityId;
  const { data: timelineData, isLoading: isLoadingActivities } = useTimeline(
    shouldFetchActivities ? 'opportunity' : '',
    shouldFetchActivities ? opportunityId! : 0
  );

  const activities = timelineData?.items || [];

  const handleEditSubmit = async (data: OpportunityFormData) => {
    if (!opportunityId) return;
    try {
      const stage = pipelineStages?.find(
        (s) => s.name.toLowerCase().replace(/\s+/g, '_') === data.stage
      );
      const updateData: OpportunityUpdate = {
        name: data.name,
        amount: data.value,
        probability: data.probability,
        expected_close_date: data.expectedCloseDate || undefined,
        pipeline_stage_id: stage?.id,
        contact_id: data.contactId ? parseInt(data.contactId, 10) : undefined,
        company_id: data.companyId ? parseInt(data.companyId, 10) : undefined,
        description: data.description,
      };
      await updateOpportunityMutation.mutateAsync({
        id: opportunityId,
        data: updateData,
      });
      setShowEditForm(false);
    } catch (err) {
      console.error('Failed to update opportunity:', err);
    }
  };

  const getInitialFormData = (): Partial<OpportunityFormData> | undefined => {
    if (!opportunity) return undefined;
    return {
      name: opportunity.name,
      value: opportunity.amount ?? 0,
      stage:
        opportunity.pipeline_stage?.name?.toLowerCase().replace(/\s+/g, '_') ??
        'qualification',
      probability: opportunity.probability ?? 0,
      expectedCloseDate: opportunity.expected_close_date ?? '',
      contactId: opportunity.contact_id ? String(opportunity.contact_id) : '',
      companyId: opportunity.company_id ? String(opportunity.company_id) : '',
      description: opportunity.description ?? '',
    };
  };

  const handleDeleteConfirm = async () => {
    if (!opportunityId) return;
    try {
      await deleteOpportunityMutation.mutateAsync(opportunityId);
      navigate('/opportunities');
    } catch {
      // Error handled by mutation
    }
  };

  // Build contacts and companies lists for form dropdowns
  const contactsList = (contactsData?.items ?? []).map((contact) => ({
    id: String(contact.id),
    name: `${contact.first_name} ${contact.last_name}`,
  }));

  const companiesList = (companiesData?.items ?? []).map((company) => ({
    id: String(company.id),
    name: company.name,
  }));

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  const errorMessage =
    error instanceof Error ? error.message : error ? String(error) : null;

  if (errorMessage || !opportunity) {
    return (
      <div className="rounded-md bg-red-50 p-4">
        <div className="flex">
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800">
              {errorMessage || 'Opportunity not found'}
            </h3>
            <div className="mt-4">
              <Link
                to="/opportunities"
                className="text-red-600 hover:text-red-500"
              >
                Back to opportunities
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const stageName =
    opportunity.pipeline_stage?.name?.toLowerCase().replace(/\s+/g, '_') ?? '';

  const tabs: { id: TabType; name: string }[] = [
    { id: 'details', name: 'Details' },
    { id: 'activities', name: 'Activities' },
    { id: 'notes', name: 'Notes' },
    { id: 'attachments', name: 'Attachments' },
    { id: 'comments', name: 'Comments' },
    { id: 'history', name: 'History' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center space-x-4">
          <Link
            to="/opportunities"
            className="text-gray-400 hover:text-gray-500 flex-shrink-0"
          >
            <svg
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10 19l-7-7m0 0l7-7m-7 7h18"
              />
            </svg>
          </Link>
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl font-bold text-gray-900 truncate">
              {opportunity.name}
            </h1>
            <div className="flex flex-wrap items-center gap-2 mt-1">
              <span
                className={getStatusBadgeClasses(stageName, 'opportunity')}
              >
                {opportunity.pipeline_stage?.name || stageName}
              </span>
              {opportunity.company?.name && (
                <span className="text-sm text-gray-500">
                  {opportunity.company.name}
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <Button
            variant="secondary"
            onClick={() => setShowEditForm(true)}
            className="flex-1 sm:flex-none"
          >
            Edit
          </Button>
          <Button
            variant="danger"
            onClick={() => setShowDeleteConfirm(true)}
            isLoading={deleteOpportunityMutation.isPending}
            className="flex-1 sm:flex-none"
          >
            Delete
          </Button>
        </div>
      </div>

      {/* AI Suggestions */}
      <NextBestActionCard entityType="opportunity" entityId={opportunity.id} />
      <AIInsightsCard
        entityType="opportunity"
        entityId={opportunity.id}
        variant="inline"
        entityName={opportunity.name}
      />

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
      {activeTab === 'details' && (
        <div className="bg-white shadow rounded-lg">
          <div className="p-4 sm:p-6">
            <dl className="grid grid-cols-1 gap-4 sm:gap-x-4 sm:gap-y-6 sm:grid-cols-2">
              <div>
                <dt className="text-sm font-medium text-gray-500">Value</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {opportunity.amount
                    ? formatCurrency(opportunity.amount)
                    : '-'}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">
                  Probability
                </dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {opportunity.probability != null
                    ? formatPercentage(opportunity.probability)
                    : '-'}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">
                  Weighted Value
                </dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {opportunity.weighted_amount
                    ? formatCurrency(opportunity.weighted_amount)
                    : '-'}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Stage</dt>
                <dd className="mt-1">
                  <span
                    className={getStatusBadgeClasses(stageName, 'opportunity')}
                  >
                    {opportunity.pipeline_stage?.name || '-'}
                  </span>
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">
                  Expected Close Date
                </dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {formatDate(opportunity.expected_close_date) || '-'}
                </dd>
              </div>

              {opportunity.actual_close_date && (
                <div>
                  <dt className="text-sm font-medium text-gray-500">
                    Actual Close Date
                  </dt>
                  <dd className="mt-1 text-sm text-gray-900">
                    {formatDate(opportunity.actual_close_date)}
                  </dd>
                </div>
              )}

              <div>
                <dt className="text-sm font-medium text-gray-500">Contact</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {opportunity.contact ? (
                    <Link
                      to={`/contacts/${opportunity.contact.id}`}
                      className="text-primary-600 hover:text-primary-500"
                    >
                      {opportunity.contact.full_name}
                    </Link>
                  ) : (
                    '-'
                  )}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Company</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {opportunity.company ? (
                    <Link
                      to={`/companies/${opportunity.company.id}`}
                      className="text-primary-600 hover:text-primary-500"
                    >
                      {opportunity.company.name}
                    </Link>
                  ) : (
                    '-'
                  )}
                </dd>
              </div>

              <div className="sm:col-span-2">
                <dt className="text-sm font-medium text-gray-500">
                  Description
                </dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {opportunity.description || 'No description'}
                </dd>
              </div>

              {opportunity.loss_reason && (
                <div className="sm:col-span-2">
                  <dt className="text-sm font-medium text-gray-500">
                    Loss Reason
                  </dt>
                  <dd className="mt-1 text-sm text-gray-900">
                    {opportunity.loss_reason}
                    {opportunity.loss_notes && (
                      <p className="mt-1 text-gray-600">
                        {opportunity.loss_notes}
                      </p>
                    )}
                  </dd>
                </div>
              )}

              <div>
                <dt className="text-sm font-medium text-gray-500">Created</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {formatDate(opportunity.created_at)}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">
                  Last Updated
                </dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {formatDate(opportunity.updated_at)}
                </dd>
              </div>
            </dl>
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

      {activeTab === 'notes' && opportunityId && (
        <Suspense fallback={<div className="bg-white shadow rounded-lg p-6 animate-pulse"><div className="h-4 bg-gray-200 rounded w-1/3 mb-4" /><div className="space-y-3"><div className="h-3 bg-gray-200 rounded" /><div className="h-3 bg-gray-200 rounded w-5/6" /></div></div>}>
          <NotesList entityType="opportunity" entityId={opportunityId} />
        </Suspense>
      )}

      {activeTab === 'attachments' && opportunityId && (
        <Suspense fallback={<div className="bg-white shadow rounded-lg p-6 animate-pulse"><div className="h-4 bg-gray-200 rounded w-1/3 mb-4" /><div className="space-y-3"><div className="h-3 bg-gray-200 rounded" /><div className="h-3 bg-gray-200 rounded w-5/6" /></div></div>}>
          <AttachmentList entityType="opportunities" entityId={opportunityId} />
        </Suspense>
      )}

      {/* Comments Tab */}
      {activeTab === 'comments' && opportunityId && (
        <Suspense fallback={<div className="bg-white shadow rounded-lg p-6 animate-pulse"><div className="h-4 bg-gray-200 rounded w-1/3 mb-4" /><div className="space-y-3"><div className="h-3 bg-gray-200 rounded" /><div className="h-3 bg-gray-200 rounded w-5/6" /></div></div>}>
          <CommentSection entityType="opportunities" entityId={opportunityId} />
        </Suspense>
      )}

      {/* History Tab */}
      {activeTab === 'history' && opportunityId && (
        <Suspense fallback={<div className="bg-white shadow rounded-lg p-6 animate-pulse"><div className="h-4 bg-gray-200 rounded w-1/3 mb-4" /><div className="space-y-3"><div className="h-3 bg-gray-200 rounded" /><div className="h-3 bg-gray-200 rounded w-5/6" /></div></div>}>
          <AuditTimeline entityType="opportunities" entityId={opportunityId} />
        </Suspense>
      )}

      {/* Edit Form Modal */}
      <Modal
        isOpen={showEditForm}
        onClose={() => setShowEditForm(false)}
        title="Edit Opportunity"
        size="full"
        fullScreenOnMobile
      >
        <OpportunityForm
          initialData={getInitialFormData()}
          onSubmit={handleEditSubmit}
          onCancel={() => setShowEditForm(false)}
          isLoading={updateOpportunityMutation.isPending}
          submitLabel="Update Opportunity"
          contacts={contactsList}
          companies={companiesList}
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDeleteConfirm}
        title="Delete Opportunity"
        message={`Are you sure you want to delete "${opportunity.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteOpportunityMutation.isPending}
      />
    </div>
  );
}

export default OpportunityDetailPage;

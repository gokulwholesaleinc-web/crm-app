import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Button, Spinner, Modal, ConfirmDialog } from '../../components/ui';
import { NotesList } from '../../components/shared';
import { ConvertLeadModal } from './components/ConvertLeadModal';
import { LeadForm, LeadFormData } from './components/LeadForm';
import { AIInsightsCard, NextBestActionCard } from '../../components/ai';
import { getStatusBadgeClasses, formatStatusLabel, getScoreColor } from '../../utils';
import { formatDate, formatPhoneNumber } from '../../utils/formatters';
import { useLead, useDeleteLead, useConvertLead, useUpdateLead } from '../../hooks';
import { useTimeline } from '../../hooks/useActivities';
import type { LeadUpdate } from '../../types';
import clsx from 'clsx';

type TabType = 'details' | 'activities' | 'notes';

function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const leadId = id ? parseInt(id, 10) : undefined;
  const [activeTab, setActiveTab] = useState<TabType>('details');
  const [showConvertModal, setShowConvertModal] = useState(false);
  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Use hooks for data fetching
  const { data: lead, isLoading, error } = useLead(leadId);
  const deleteLeadMutation = useDeleteLead();
  const convertLeadMutation = useConvertLead();
  const updateLeadMutation = useUpdateLead();

  // Fetch timeline/activities - only when on activities tab
  const shouldFetchActivities = activeTab === 'activities' && !!leadId;
  const { data: timelineData, isLoading: isLoadingActivities } = useTimeline(
    shouldFetchActivities ? 'lead' : '',
    shouldFetchActivities ? leadId! : 0
  );

  const activities = timelineData?.items || [];

  const handleEditSubmit = async (data: LeadFormData) => {
    if (!leadId) return;
    try {
      const updateData: LeadUpdate = {
        first_name: data.firstName,
        last_name: data.lastName,
        email: data.email,
        phone: data.phone || undefined,
        company_name: data.company || undefined,
        job_title: data.jobTitle || undefined,
        status: data.status,
      };
      await updateLeadMutation.mutateAsync({
        id: leadId,
        data: updateData,
      });
      setShowEditForm(false);
    } catch (err) {
      console.error('Failed to update lead:', err);
    }
  };

  const getInitialFormData = (): Partial<LeadFormData> | undefined => {
    if (!lead) return undefined;
    return {
      firstName: lead.first_name,
      lastName: lead.last_name,
      email: lead.email || '',
      phone: lead.phone || '',
      company: lead.company_name || '',
      jobTitle: lead.job_title || '',
      status: lead.status,
      source: lead.source?.name || '',
      notes: lead.description || '',
    };
  };

  const handleDeleteConfirm = async () => {
    if (!leadId) return;

    try {
      await deleteLeadMutation.mutateAsync(leadId);
      navigate('/leads');
    } catch {
      // Error handled by mutation
    }
  };

  const handleConvert = async (data: {
    createContact: boolean;
    createOpportunity: boolean;
    opportunityName?: string;
    opportunityValue?: number;
    opportunityStage?: string;
  }) => {
    if (!leadId) return;

    try {
      // Map stage string to stage ID (using default stage 1 for now)
      // In a production app, you'd fetch pipeline stages and map properly
      const stageMapping: Record<string, number> = {
        qualification: 1,
        proposal: 2,
        negotiation: 3,
        closed_won: 4,
        closed_lost: 5,
      };
      const stageId = data.opportunityStage ? (stageMapping[data.opportunityStage] || 1) : 1;

      const result = await convertLeadMutation.mutateAsync({
        leadId: leadId,
        data: {
          pipeline_stage_id: stageId,
          create_company: data.createContact,
        },
      });

      // Navigate to the appropriate page based on what was created
      if (result.contact_id) {
        navigate(`/contacts/${result.contact_id}`);
      } else if (result.opportunity_id) {
        navigate(`/opportunities`);
      } else {
        navigate('/leads');
      }
    } catch {
      // Error handled by mutation
      throw new Error('Failed to convert lead');
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  const errorMessage = error instanceof Error ? error.message : error ? String(error) : null;

  if (errorMessage || !lead) {
    return (
      <div className="rounded-md bg-red-50 p-4">
        <div className="flex">
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800">
              {errorMessage || 'Lead not found'}
            </h3>
            <div className="mt-4">
              <Link to="/leads" className="text-red-600 hover:text-red-500">
                Back to leads
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const tabs: { id: TabType; name: string }[] = [
    { id: 'details', name: 'Details' },
    { id: 'activities', name: 'Activities' },
    { id: 'notes', name: 'Notes' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center space-x-3 sm:space-x-4">
          <Link to="/leads" className="text-gray-400 hover:text-gray-500 p-1 -ml-1">
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
              {lead.first_name} {lead.last_name}
            </h1>
            {lead.job_title && lead.company_name && (
              <p className="text-sm text-gray-500 truncate">
                {lead.job_title} at {lead.company_name}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 sm:gap-3">
          <AIInsightsCard
            entityType="lead"
            entityId={lead.id}
            entityName={`${lead.first_name} ${lead.last_name}`}
          />
          {lead.status === 'qualified' && (
            <Button onClick={() => setShowConvertModal(true)} className="flex-1 sm:flex-none">
              <svg
                className="h-5 w-5 mr-1 sm:mr-2"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span className="hidden sm:inline">Convert Lead</span>
              <span className="sm:hidden">Convert</span>
            </Button>
          )}
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
            isLoading={deleteLeadMutation.isPending}
            className="flex-1 sm:flex-none"
          >
            Delete
          </Button>
        </div>
      </div>

      {/* Next Best Action Suggestion */}
      <NextBestActionCard entityType="lead" entityId={lead.id} />

      {/* Lead Score Card */}
      <div className="bg-white shadow rounded-lg p-4 sm:p-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h3 className="text-lg font-medium text-gray-900">Lead Score</h3>
            <p className="text-sm text-gray-500">
              Based on engagement and fit criteria
            </p>
          </div>
          <div className="flex items-center justify-center sm:justify-end gap-4 sm:space-x-4">
            <div className="text-center">
              <div
                className={clsx(
                  'text-3xl sm:text-4xl font-bold',
                  getScoreColor(lead.score)
                )}
              >
                {lead.score}
              </div>
              <div className="text-xs sm:text-sm text-gray-500">out of 100</div>
            </div>
            <div className="w-24 h-24 sm:w-32 sm:h-32 relative flex-shrink-0">
              <svg className="w-full h-full transform -rotate-90" viewBox="0 0 128 128">
                <circle
                  cx="64"
                  cy="64"
                  r="56"
                  stroke="currentColor"
                  strokeWidth="8"
                  fill="none"
                  className="text-gray-200"
                />
                <circle
                  cx="64"
                  cy="64"
                  r="56"
                  stroke="currentColor"
                  strokeWidth="8"
                  fill="none"
                  strokeDasharray={`${(lead.score / 100) * 352} 352`}
                  className={clsx({
                    'text-green-500': lead.score >= 80,
                    'text-yellow-500': lead.score >= 60 && lead.score < 80,
                    'text-orange-500': lead.score >= 40 && lead.score < 60,
                    'text-red-500': lead.score < 40,
                  })}
                />
              </svg>
            </div>
          </div>
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
      {activeTab === 'details' && (
        <div className="bg-white shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              Lead Details
            </h3>
            <dl className="grid grid-cols-1 gap-4 sm:gap-x-4 sm:gap-y-6 sm:grid-cols-2">
              <div>
                <dt className="text-sm font-medium text-gray-500">Email</dt>
                <dd className="mt-1 text-sm text-gray-900 break-all">
                  <a
                    href={`mailto:${lead.email}`}
                    className="text-primary-600 hover:text-primary-500"
                  >
                    {lead.email}
                  </a>
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Phone</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {lead.phone ? (
                    <a
                      href={`tel:${lead.phone}`}
                      className="text-primary-600 hover:text-primary-500"
                    >
                      {formatPhoneNumber(lead.phone)}
                    </a>
                  ) : (
                    '-'
                  )}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Company</dt>
                <dd className="mt-1 text-sm text-gray-900 break-words">
                  {lead.company_name || '-'}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Job Title</dt>
                <dd className="mt-1 text-sm text-gray-900 break-words">
                  {lead.job_title || '-'}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Status</dt>
                <dd className="mt-1">
                  <span className={getStatusBadgeClasses(lead.status, 'lead')}>
                    {formatStatusLabel(lead.status)}
                  </span>
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Source</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {lead.source?.name ? formatStatusLabel(lead.source.name) : '-'}
                </dd>
              </div>

              <div className="sm:col-span-2">
                <dt className="text-sm font-medium text-gray-500">Description</dt>
                <dd className="mt-1 text-sm text-gray-900 break-words">
                  {lead.description || 'No description'}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Created</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {formatDate(lead.created_at)}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Last Updated</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {formatDate(lead.updated_at)}
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

      {activeTab === 'notes' && leadId && (
        <NotesList entityType="lead" entityId={leadId} />
      )}

      {/* Convert Lead Modal */}
      <ConvertLeadModal
        isOpen={showConvertModal}
        leadId={String(lead.id)}
        leadName={`${lead.first_name} ${lead.last_name}`}
        onClose={() => setShowConvertModal(false)}
        onConvert={handleConvert}
      />

      {/* Edit Form Modal */}
      <Modal
        isOpen={showEditForm}
        onClose={() => setShowEditForm(false)}
        title="Edit Lead"
        size="lg"
        fullScreenOnMobile
      >
        <LeadForm
          initialData={getInitialFormData()}
          onSubmit={handleEditSubmit}
          onCancel={() => setShowEditForm(false)}
          isLoading={updateLeadMutation.isPending}
          submitLabel="Update Lead"
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDeleteConfirm}
        title="Delete Lead"
        message={`Are you sure you want to delete ${lead.first_name} ${lead.last_name}? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteLeadMutation.isPending}
      />
    </div>
  );
}

export default LeadDetailPage;

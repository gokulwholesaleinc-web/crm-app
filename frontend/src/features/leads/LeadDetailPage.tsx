import { useState, Suspense, useRef } from 'react';
import { lazy } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useSmartBack } from '../../hooks/useSmartBack';
import { useUrlTabState } from '../../hooks/useUrlTabState';
import { Button, CopyButton, Spinner, Modal, ConfirmDialog } from '../../components/ui';
import { TabBar, ActivitiesTab, CommonTabContent, SuspenseFallback } from '../../components/shared/DetailPageShell';
import { StickyActionBar } from '../../components/shared/StickyActionBar';
import { EmailComposeModal, EmailHistory } from '../../components/email';
import { ConvertLeadModal } from './components/ConvertLeadModal';
import { LeadForm, LeadFormData } from './components/LeadForm';
import { AIInsightsCard, NextBestActionCard } from '../../components/ai';
import { getStatusBadgeClasses, formatStatusLabel, getScoreColor } from '../../utils';
import { showError } from '../../utils/toast';
import { formatDate, formatPhoneNumber } from '../../utils/formatters';
import { useLead, useDeleteLead, useConvertLead, useUpdateLead } from '../../hooks/useLeads';
import type { LeadUpdate } from '../../types';
import clsx from 'clsx';

const CommentSection = lazy(() => import('../../components/shared/CommentSection'));

type TabType = 'details' | 'activities' | 'notes' | 'emails' | 'attachments' | 'comments' | 'history' | 'sharing';

const TABS: { id: TabType; name: string }[] = [
  { id: 'details', name: 'Details' },
  { id: 'activities', name: 'Activities' },
  { id: 'notes', name: 'Notes' },
  { id: 'emails', name: 'Emails' },
  { id: 'attachments', name: 'Attachments' },
  { id: 'comments', name: 'Comments' },
  { id: 'history', name: 'History' },
  { id: 'sharing', name: 'Sharing' },
];

const TAB_IDS: ReadonlySet<TabType> = new Set(TABS.map((t) => t.id));

function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const handleBack = useSmartBack('/leads');
  const leadId = id ? parseInt(id, 10) : undefined;
  const [activeTab, handleTabChange] = useUrlTabState<TabType>(TAB_IDS, 'details');
  const [showConvertModal, setShowConvertModal] = useState(false);
  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showEmailCompose, setShowEmailCompose] = useState(false);
  const actionRowRef = useRef<HTMLDivElement>(null);

  const { data: lead, isLoading, error } = useLead(leadId);
  const deleteLeadMutation = useDeleteLead();
  const convertLeadMutation = useConvertLead();
  const updateLeadMutation = useUpdateLead();

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
      };
      // Only include status when it actually changed. The backend rejects
      // status='converted' direct edits, so re-asserting an existing
      // 'converted' status from an orphan-converted row would 400 every
      // unrelated edit (e.g. fixing a typo) until the lead is properly
      // converted. Same logic generalises to other status values.
      if (data.status && data.status !== lead?.status) {
        updateData.status = data.status;
      }
      await updateLeadMutation.mutateAsync({
        id: leadId,
        data: updateData,
      });
      setShowEditForm(false);
    } catch (err) {
      showError('Failed to update lead');
    }
  };

  const getInitialFormData = (): Partial<LeadFormData> | undefined => {
    if (!lead) return undefined;
    return {
      firstName: lead.first_name || '',
      lastName: lead.last_name || '',
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
    opportunityStage?: number;
  }) => {
    if (!leadId) return;
    try {
      const stageId = data.opportunityStage ?? 1;
      const result = await convertLeadMutation.mutateAsync({
        leadId: leadId,
        data: {
          pipeline_stage_id: stageId,
          create_company: data.createContact,
        },
      });
      if (result.contact_id) {
        navigate(`/contacts/${result.contact_id}`);
      } else if (result.opportunity_id) {
        navigate(`/opportunities`);
      } else {
        navigate('/leads');
      }
    } catch {
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
      <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
        <div className="flex">
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800 dark:text-red-300">
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

  // The lead's status was flipped to 'converted' (e.g. via the edit form
  // before the server-side guard landed) but the Convert flow never ran,
  // so no Contact / Opportunity exists. Surface a banner that lets the
  // user run conversion now and re-enable the Convert button below.
  const isOrphanConverted =
    lead.status === 'converted' && !lead.converted_contact_id;

  return (
    <div className="space-y-6">
      <StickyActionBar triggerRef={actionRowRef}>
        <Button
          variant="primary"
          size="sm"
          onClick={() => setShowEmailCompose(true)}
          disabled={!lead.email}
        >
          Send Email
        </Button>
        {(lead.status === 'qualified' || isOrphanConverted) && (
          <Button size="sm" onClick={() => setShowConvertModal(true)}>
            {isOrphanConverted ? 'Run Conversion' : 'Convert'}
          </Button>
        )}
        <Button variant="secondary" size="sm" onClick={() => setShowEditForm(true)}>
          Edit
        </Button>
      </StickyActionBar>
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center space-x-3 sm:space-x-4">
          <button type="button" onClick={handleBack} className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300 p-1 -ml-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded" aria-label="Go back">
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100 truncate">
                {lead.full_name || 'Unnamed Lead'}
              </h1>
              <span className="inline-flex items-center gap-1">
                <span className="text-xs font-mono text-gray-500 dark:text-gray-400">#{lead.id}</span>
                <CopyButton value={String(lead.id)} label="ID" />
              </span>
            </div>
            {lead.job_title && lead.company_name && (
              <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                {lead.job_title} at {lead.company_name}
              </p>
            )}
          </div>
        </div>
        <div ref={actionRowRef} className="flex items-center gap-2 sm:gap-3">
          <Button
            variant="primary"
            onClick={() => setShowEmailCompose(true)}
            disabled={!lead.email}
            title={lead.email ? undefined : 'Add an email address to this lead before sending'}
            className="flex-1 sm:flex-none"
          >
            Send Email
          </Button>
          <AIInsightsCard entityType="lead" entityId={lead.id} entityName={lead.full_name || 'Lead'} />
          {(lead.status === 'qualified' || isOrphanConverted) && (
            <Button onClick={() => setShowConvertModal(true)} className="flex-1 sm:flex-none">
              <svg className="h-5 w-5 mr-1 sm:mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="hidden sm:inline">
                {isOrphanConverted ? 'Run Conversion' : 'Convert Lead'}
              </span>
              <span className="sm:hidden">Convert</span>
            </Button>
          )}
          <Button variant="secondary" onClick={() => setShowEditForm(true)} className="flex-1 sm:flex-none">
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

      {isOrphanConverted && (
        <div
          role="alert"
          aria-live="polite"
          className="rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/30 px-4 py-3 text-sm text-amber-900 dark:text-amber-100"
        >
          <p className="font-semibold">Lead is marked Converted but conversion never ran.</p>
          <p className="mt-1">
            No Contact or Opportunity was created. Click <span className="font-medium">Run Conversion</span>{' '}
            in the header to create them now.
          </p>
        </div>
      )}

      {/* Next Best Action Suggestion */}
      <NextBestActionCard entityType="lead" entityId={lead.id} />

      {/* Lead Score Card */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 sm:p-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Lead Score</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">Based on engagement and fit criteria</p>
          </div>
          <div className="flex items-center justify-center sm:justify-end gap-4 sm:space-x-4">
            <div className="text-center">
              <div className={clsx('text-3xl sm:text-4xl font-bold', getScoreColor(lead.score))}>
                {lead.score}
              </div>
              <div className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">out of 100</div>
            </div>
            <div className="w-24 h-24 sm:w-32 sm:h-32 relative flex-shrink-0">
              <svg className="w-full h-full transform -rotate-90" viewBox="0 0 128 128">
                <circle cx="64" cy="64" r="56" stroke="currentColor" strokeWidth="8" fill="none" className="text-gray-200 dark:text-gray-700" />
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
      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={handleTabChange} />

      {/* Tab Content */}
      {activeTab === 'details' && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-4">Lead Details</h3>
            <dl className="grid grid-cols-1 gap-4 sm:gap-x-4 sm:gap-y-6 sm:grid-cols-2">
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Email</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100 break-all flex items-center gap-2">
                  <a href={`mailto:${lead.email}`} className="text-primary-600 hover:text-primary-500">
                    {lead.email}
                  </a>
                  {lead.email && <CopyButton value={lead.email} label="email" />}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Phone</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100 flex items-center gap-2">
                  {lead.phone ? (
                    <>
                      <a href={`tel:${lead.phone}`} className="text-primary-600 hover:text-primary-500">
                        {formatPhoneNumber(lead.phone)}
                      </a>
                      <CopyButton value={lead.phone} label="phone" />
                    </>
                  ) : '-'}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Company</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100 break-words">{lead.company_name || '-'}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Job Title</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100 break-words">{lead.job_title || '-'}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Status</dt>
                <dd className="mt-1">
                  <span className={getStatusBadgeClasses(lead.status, 'lead')}>{formatStatusLabel(lead.status)}</span>
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Source</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                  {lead.source?.name ? formatStatusLabel(lead.source.name) : '-'}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Sales Code</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{lead.sales_code || '-'}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Description</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100 break-words">
                  {lead.description || 'No description'}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Created</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{formatDate(lead.created_at)}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Last Updated</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{formatDate(lead.updated_at)}</dd>
              </div>
              {(lead.converted_contact_id || lead.converted_opportunity_id) && (
                <>
                  <div className="sm:col-span-2 pt-4 border-t border-gray-200 dark:border-gray-700">
                    <dt className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">Converted Entities</dt>
                  </div>
                  {lead.converted_contact_id && (
                    <div>
                      <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Contact</dt>
                      <dd className="mt-1 text-sm">
                        <Link to={`/contacts/${lead.converted_contact_id}`} className="text-primary-600 hover:text-primary-900 dark:hover:text-primary-300">
                          View Contact #{lead.converted_contact_id}
                        </Link>
                      </dd>
                    </div>
                  )}
                  {lead.converted_opportunity_id && (
                    <div>
                      <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Opportunity</dt>
                      <dd className="mt-1 text-sm">
                        <Link to={`/opportunities/${lead.converted_opportunity_id}`} className="text-primary-600 hover:text-primary-900 dark:hover:text-primary-300">
                          View Opportunity #{lead.converted_opportunity_id}
                        </Link>
                      </dd>
                    </div>
                  )}
                </>
              )}
            </dl>
          </div>
        </div>
      )}

      {activeTab === 'activities' && leadId && (
        <ActivitiesTab entityType="lead" entityId={leadId} />
      )}

      {activeTab === 'emails' && leadId && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <EmailHistory entityType="leads" entityId={leadId} />
          </div>
        </div>
      )}

      {leadId && (
        <>
          <CommonTabContent
            activeTab={activeTab}
            entityType="leads"
            entityId={leadId}
            enabledTabs={['notes', 'attachments', 'history', 'sharing']}
          />
          {activeTab === 'comments' && (
            <Suspense fallback={<SuspenseFallback />}>
              <CommentSection entityType="leads" entityId={leadId} />
            </Suspense>
          )}
        </>
      )}

      {/* Email Compose Modal */}
      <EmailComposeModal
        isOpen={showEmailCompose}
        onClose={() => setShowEmailCompose(false)}
        defaultTo={lead.email || ''}
        entityType="leads"
        entityId={leadId}
      />

      {/* Convert Lead Modal */}
      <ConvertLeadModal
        isOpen={showConvertModal}
        leadId={String(lead.id)}
        leadName={lead.full_name || 'Lead'}
        onClose={() => setShowConvertModal(false)}
        onConvert={handleConvert}
      />

      {/* Edit Form Modal */}
      <Modal isOpen={showEditForm} onClose={() => setShowEditForm(false)} title="Edit Lead" size="lg" fullScreenOnMobile>
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
        message={`Are you sure you want to delete ${lead.full_name || 'this lead'}? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteLeadMutation.isPending}
      />
    </div>
  );
}

export default LeadDetailPage;

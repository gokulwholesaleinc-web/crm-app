import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useSmartBack } from '../../hooks/useSmartBack';
import { Button, EntityLink, Spinner, Modal, ConfirmDialog } from '../../components/ui';
import { TabBar, ActivitiesTab, CommonTabContent } from '../../components/shared/DetailPageShell';
import { OpportunityForm, OpportunityFormData } from './components/OpportunityForm';
import { AIInsightsCard, NextBestActionCard } from '../../components/ai';
import { useOpportunity, useDeleteOpportunity, useUpdateOpportunity } from '../../hooks/useOpportunities';
import { useQuotes } from '../../hooks/useQuotes';
import { useProposals } from '../../hooks/useProposals';
import { usePayments } from '../../hooks/usePayments';
import { formatCurrency, formatDate, formatPercentage } from '../../utils/formatters';
import { getStatusBadgeClasses } from '../../utils';
import { showError } from '../../utils/toast';
import type { OpportunityUpdate, Quote, Proposal, Payment } from '../../types';
import clsx from 'clsx';

type TabType = 'details' | 'activities' | 'quotes' | 'proposals' | 'payments' | 'notes' | 'attachments' | 'comments' | 'history' | 'sharing';

const TABS: { id: TabType; name: string }[] = [
  { id: 'details', name: 'Details' },
  { id: 'activities', name: 'Activities' },
  { id: 'quotes', name: 'Quotes' },
  { id: 'proposals', name: 'Proposals' },
  { id: 'payments', name: 'Payments' },
  { id: 'notes', name: 'Notes' },
  { id: 'attachments', name: 'Attachments' },
  { id: 'comments', name: 'Comments' },
  { id: 'history', name: 'History' },
  { id: 'sharing', name: 'Sharing' },
];

function OpportunityDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const handleBack = useSmartBack('/opportunities');
  const opportunityId = id ? parseInt(id, 10) : undefined;
  const [activeTab, setActiveTab] = useState<TabType>('details');
  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const { data: opportunity, isLoading, error } = useOpportunity(opportunityId);
  const deleteOpportunityMutation = useDeleteOpportunity();
  const updateOpportunityMutation = useUpdateOpportunity();

  const shouldFetchQuotes = activeTab === 'quotes' && !!opportunityId;
  const { data: quotesData, isLoading: isLoadingQuotes } = useQuotes(
    shouldFetchQuotes ? { opportunity_id: opportunityId, page_size: 50 } : undefined
  );

  const shouldFetchProposals = activeTab === 'proposals' && !!opportunityId;
  const { data: proposalsData, isLoading: isLoadingProposals } = useProposals(
    shouldFetchProposals ? { opportunity_id: opportunityId, page_size: 50 } : undefined
  );

  const shouldFetchPayments = activeTab === 'payments' && !!opportunityId;
  const { data: paymentsData, isLoading: isLoadingPayments } = usePayments(
    shouldFetchPayments ? { opportunity_id: opportunityId, page_size: 50 } : undefined
  );

  const quotes = quotesData?.items ?? [];
  const proposals = proposalsData?.items ?? [];
  const payments = paymentsData?.items ?? [];

  const handleEditSubmit = async (data: OpportunityFormData) => {
    if (!opportunityId) return;
    try {
      const updateData: OpportunityUpdate = {
        name: data.name,
        amount: data.value,
        probability: data.probability,
        expected_close_date: data.expectedCloseDate || undefined,
        pipeline_stage_id: data.stage,
        contact_id: data.contactId ? parseInt(data.contactId, 10) : undefined,
        company_id: data.companyId ? parseInt(data.companyId, 10) : undefined,
        description: data.description,
      };
      await updateOpportunityMutation.mutateAsync({ id: opportunityId, data: updateData });
      setShowEditForm(false);
    } catch (err) {
      showError('Failed to update opportunity');
    }
  };

  const getInitialFormData = (): Partial<OpportunityFormData> | undefined => {
    if (!opportunity) return undefined;
    return {
      name: opportunity.name,
      value: opportunity.amount ?? 0,
      stage: opportunity.pipeline_stage_id,
      probability: opportunity.probability ?? 0,
      expectedCloseDate: opportunity.expected_close_date ?? '',
      contactId: opportunity.contact_id != null ? String(opportunity.contact_id) : undefined,
      companyId: opportunity.company_id != null ? String(opportunity.company_id) : undefined,
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  const errorMessage = error instanceof Error ? error.message : error ? String(error) : null;

  if (errorMessage || !opportunity) {
    return (
      <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
        <div className="flex">
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800 dark:text-red-300">
              {errorMessage || 'Opportunity not found'}
            </h3>
            <div className="mt-4">
              <Link to="/opportunities" className="text-red-600 hover:text-red-500 dark:text-red-400 dark:hover:text-red-300">
                Back to opportunities
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const stageName = opportunity.pipeline_stage?.name?.toLowerCase().replace(/\s+/g, '_') ?? '';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center space-x-4">
          <button
            type="button"
            onClick={handleBack}
            className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300 flex-shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded"
            aria-label="Go back"
          >
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </button>
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100 truncate">
              {opportunity.name}
            </h1>
            <div className="flex flex-wrap items-center gap-2 mt-1">
              <span className={getStatusBadgeClasses(stageName, 'opportunity')}>
                {opportunity.pipeline_stage?.name || stageName}
              </span>
              {opportunity.company?.name && (
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  <EntityLink type="company" id={opportunity.company.id} variant="muted">
                    {opportunity.company.name}
                  </EntityLink>
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <Button variant="secondary" onClick={() => setShowEditForm(true)} className="flex-1 sm:flex-none">
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

      {/* Quick Actions */}
      <div className="flex flex-wrap gap-2">
        <Link to={`/quotes?opportunity_id=${opportunity.id}`}>
          <Button variant="secondary" className="text-sm">
            <svg className="h-4 w-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Create Quote
          </Button>
        </Link>
        <Link to={`/proposals?opportunity_id=${opportunity.id}`}>
          <Button variant="secondary" className="text-sm">
            <svg className="h-4 w-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            Generate Proposal
          </Button>
        </Link>
        <Link to="/payments">
          <Button variant="secondary" className="text-sm">
            <svg className="h-4 w-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
            </svg>
            Collect Payment
          </Button>
        </Link>
      </div>

      {/* AI Suggestions */}
      <NextBestActionCard entityType="opportunity" entityId={opportunity.id} />
      <AIInsightsCard entityType="opportunity" entityId={opportunity.id} variant="inline" entityName={opportunity.name} />

      {/* Tabs */}
      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Tab Content */}
      {activeTab === 'details' && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
          <div className="p-4 sm:p-6">
            <dl className="grid grid-cols-1 gap-4 sm:gap-x-4 sm:gap-y-6 sm:grid-cols-2">
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Value</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                  {opportunity.amount ? formatCurrency(opportunity.amount, opportunity.currency) : '-'}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Probability</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                  {opportunity.probability != null ? formatPercentage(opportunity.probability) : '-'}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Weighted Value</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                  {opportunity.weighted_amount ? formatCurrency(opportunity.weighted_amount, opportunity.currency) : '-'}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Stage</dt>
                <dd className="mt-1">
                  <span className={getStatusBadgeClasses(stageName, 'opportunity')}>
                    {opportunity.pipeline_stage?.name || '-'}
                  </span>
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Expected Close Date</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                  {formatDate(opportunity.expected_close_date) || '-'}
                </dd>
              </div>
              {opportunity.actual_close_date && (
                <div>
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Actual Close Date</dt>
                  <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                    {formatDate(opportunity.actual_close_date)}
                  </dd>
                </div>
              )}
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Contact</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                  {opportunity.contact ? (
                    <Link to={`/contacts/${opportunity.contact.id}`} className="text-primary-600 hover:text-primary-500 dark:text-primary-400 dark:hover:text-primary-300">
                      {opportunity.contact.full_name}
                    </Link>
                  ) : '-'}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Company</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                  {opportunity.company ? (
                    <Link to={`/companies/${opportunity.company.id}`} className="text-primary-600 hover:text-primary-500 dark:text-primary-400 dark:hover:text-primary-300">
                      {opportunity.company.name}
                    </Link>
                  ) : '-'}
                </dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Description</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                  {opportunity.description || 'No description'}
                </dd>
              </div>
              {opportunity.loss_reason && (
                <div className="sm:col-span-2">
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Loss Reason</dt>
                  <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                    {opportunity.loss_reason}
                    {opportunity.loss_notes && (
                      <p className="mt-1 text-gray-600 dark:text-gray-400">{opportunity.loss_notes}</p>
                    )}
                  </dd>
                </div>
              )}
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Created</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{formatDate(opportunity.created_at)}</dd>
              </div>
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Last Updated</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{formatDate(opportunity.updated_at)}</dd>
              </div>
            </dl>
          </div>
        </div>
      )}

      {activeTab === 'activities' && opportunityId && (
        <ActivitiesTab entityType="opportunity" entityId={opportunityId} />
      )}

      {activeTab === 'quotes' && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            {isLoadingQuotes ? (
              <div className="flex items-center justify-center py-4"><Spinner /></div>
            ) : quotes.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
                No quotes linked to this opportunity.
              </p>
            ) : (
              <ul className="divide-y divide-gray-200 dark:divide-gray-700">
                {quotes.map((quote: Quote) => (
                  <li key={quote.id} className="py-3 flex items-center justify-between">
                    <div className="min-w-0 flex-1">
                      <Link to={`/quotes/${quote.id}`} className="text-sm font-medium text-primary-600 hover:text-primary-500">
                        {quote.title}
                      </Link>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{quote.quote_number} - {formatDate(quote.created_at)}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {formatCurrency(quote.total, quote.currency)}
                      </span>
                      <span className={clsx(
                        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
                        quote.status === 'accepted' ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300' :
                        quote.status === 'sent' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300' :
                        quote.status === 'rejected' ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300' :
                        'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                      )}>
                        {quote.status.charAt(0).toUpperCase() + quote.status.slice(1)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {activeTab === 'proposals' && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            {isLoadingProposals ? (
              <div className="flex items-center justify-center py-4"><Spinner /></div>
            ) : proposals.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
                No proposals linked to this opportunity.
              </p>
            ) : (
              <ul className="divide-y divide-gray-200 dark:divide-gray-700">
                {proposals.map((proposal: Proposal) => (
                  <li key={proposal.id} className="py-3 flex items-center justify-between">
                    <div className="min-w-0 flex-1">
                      <Link to={`/proposals/${proposal.id}`} className="text-sm font-medium text-primary-600 hover:text-primary-500">
                        {proposal.title}
                      </Link>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{proposal.proposal_number} - {formatDate(proposal.created_at)}</p>
                    </div>
                    <span className={clsx(
                      'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
                      proposal.status === 'accepted' ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300' :
                      proposal.status === 'sent' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300' :
                      proposal.status === 'rejected' ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300' :
                      'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                    )}>
                      {(proposal.status ?? 'draft').charAt(0).toUpperCase() + (proposal.status ?? 'draft').slice(1)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {activeTab === 'payments' && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            {isLoadingPayments ? (
              <div className="flex items-center justify-center py-4"><Spinner /></div>
            ) : payments.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
                No payments linked to this opportunity.
              </p>
            ) : (
              <ul className="divide-y divide-gray-200 dark:divide-gray-700">
                {payments.map((payment: Payment) => (
                  <li key={payment.id} className="py-3 flex items-center justify-between">
                    <div className="min-w-0 flex-1">
                      <Link to={`/payments/${payment.id}`} className="text-sm font-medium text-primary-600 hover:text-primary-500">
                        Payment #{payment.id}
                      </Link>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{formatDate(payment.created_at)}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {formatCurrency(payment.amount, payment.currency)}
                      </span>
                      <span className={clsx(
                        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
                        payment.status === 'succeeded' ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300' :
                        payment.status === 'failed' ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300' :
                        'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300'
                      )}>
                        {payment.status.charAt(0).toUpperCase() + payment.status.slice(1)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {opportunityId && (
        <CommonTabContent
          activeTab={activeTab}
          entityType="opportunities"
          entityId={opportunityId}
          enabledTabs={['notes', 'attachments', 'comments', 'history', 'sharing']}
        />
      )}

      {/* Edit Form Modal */}
      <Modal isOpen={showEditForm} onClose={() => setShowEditForm(false)} title="Edit Opportunity" size="full" fullScreenOnMobile>
        <OpportunityForm
          initialData={getInitialFormData()}
          onSubmit={handleEditSubmit}
          onCancel={() => setShowEditForm(false)}
          isLoading={updateOpportunityMutation.isPending}
          submitLabel="Update Opportunity"
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

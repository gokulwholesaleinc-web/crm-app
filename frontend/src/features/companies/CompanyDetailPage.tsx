import { useState, lazy, Suspense } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSmartBack } from '../../hooks/useSmartBack';
import clsx from 'clsx';
import { BuildingOffice2Icon, ArrowLeftIcon } from '@heroicons/react/24/outline';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { Modal } from '../../components/ui/Modal';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { TabBar, ActivitiesTab, CommonTabContent, SuspenseFallback } from '../../components/shared/DetailPageShell';
import { OverviewTab } from './components/tabs/OverviewTab';
import { OpportunitiesTab } from './components/tabs/OpportunitiesTab';
import { QuotesTab } from './components/tabs/QuotesTab';
import { ProposalsTab } from './components/tabs/ProposalsTab';
import { CompanyForm } from './components/CompanyForm';
import { useCompany, useUpdateCompany, useDeleteCompany } from '../../hooks/useCompanies';
import { useContacts } from '../../hooks/useContacts';
import { useOpportunities } from '../../hooks/useOpportunities';
import { useQuotes } from '../../hooks/useQuotes';
import { useProposals } from '../../hooks/useProposals';
import { getStatusColor, formatStatusLabel } from '../../utils/statusColors';
import { showSuccess, showError } from '../../utils/toast';
import type { CompanyUpdate } from '../../types';

const ContractsList = lazy(() => import('../../components/shared/ContractsList'));
const MetaTab = lazy(() => import('./components/MetaTab'));
const ExpensesTab = lazy(() => import('./components/ExpensesTab'));
const EntityPaymentsTab = lazy(() => import('../../components/shared/EntityPaymentsTab'));

type TabType = 'overview' | 'opportunities' | 'contracts' | 'quotes' | 'proposals' | 'payments' | 'activities' | 'notes' | 'attachments' | 'history' | 'sharing' | 'meta' | 'expenses';

const TABS: { id: TabType; name: string }[] = [
  { id: 'overview', name: 'Overview' },
  { id: 'opportunities', name: 'Opportunities' },
  { id: 'contracts', name: 'Contracts' },
  { id: 'quotes', name: 'Quotes' },
  { id: 'proposals', name: 'Proposals' },
  { id: 'payments', name: 'Payments' },
  { id: 'activities', name: 'Activities' },
  { id: 'notes', name: 'Notes' },
  { id: 'attachments', name: 'Attachments' },
  { id: 'meta', name: 'Meta/Social' },
  { id: 'expenses', name: 'Expenses' },
  { id: 'history', name: 'History' },
  { id: 'sharing', name: 'Sharing' },
];

export function CompanyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const handleBack = useSmartBack('/companies');
  const companyId = id ? parseInt(id, 10) : undefined;

  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const { data: company, isLoading: isLoadingCompany } = useCompany(companyId);

  const { data: contactsData, isLoading: isLoadingContacts } = useContacts({
    company_id: companyId,
    page_size: 50,
  });

  const { data: opportunitiesData } = useOpportunities(
    activeTab === 'opportunities' && companyId ? { company_id: companyId } : undefined
  );
  const { data: quotesData } = useQuotes(
    activeTab === 'quotes' && companyId ? { company_id: companyId } : undefined
  );
  const { data: proposalsData } = useProposals(
    activeTab === 'proposals' && companyId ? { company_id: companyId } : undefined
  );
  const companyOpportunities = opportunitiesData?.items ?? [];
  const companyQuotes = quotesData?.items ?? [];
  const companyProposals = proposalsData?.items ?? [];

  const updateCompany = useUpdateCompany();
  const deleteCompany = useDeleteCompany();

  const handleDeleteConfirm = async () => {
    if (!companyId) return;
    try {
      await deleteCompany.mutateAsync(companyId);
      showSuccess('Company deleted successfully');
      navigate('/companies');
    } catch {
      showError('Failed to delete company');
    }
  };

  const handleFormSubmit = async (data: CompanyUpdate) => {
    if (!companyId) return;
    try {
      await updateCompany.mutateAsync({ id: companyId, data });
      setShowEditForm(false);
      showSuccess('Company updated successfully');
    } catch {
      showError('Failed to update company');
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
        <p className="text-gray-500 dark:text-gray-400">Company not found</p>
        <Button variant="secondary" className="mt-4" onClick={() => navigate('/companies')}>
          Back to Companies
        </Button>
      </div>
    );
  }

  const statusStyle = getStatusColor(company.status, 'company');
  const contacts = contactsData?.items || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4">
        <div className="flex items-start gap-3 sm:gap-4">
          <button
            type="button"
            onClick={handleBack}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors flex-shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            aria-label="Go back"
          >
            <ArrowLeftIcon className="h-5 w-5 text-gray-500" />
          </button>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4 flex-1 min-w-0">
            {company.logo_url ? (
              <img
                src={company.logo_url}
                alt={company.name}
                width={64}
                height={64}
                className="h-12 w-12 sm:h-16 sm:w-16 rounded-lg object-cover flex-shrink-0"
              />
            ) : (
              <div className="h-12 w-12 sm:h-16 sm:w-16 rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center flex-shrink-0">
                <BuildingOffice2Icon className="h-6 w-6 sm:h-8 sm:w-8 text-gray-400" />
              </div>
            )}
            <div className="min-w-0">
              <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100 truncate">{company.name}</h1>
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
                  <span className="text-sm text-gray-500 dark:text-gray-400 capitalize">{company.industry}</span>
                )}
              </div>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto sm:ml-auto">
          <Button
            variant="secondary"
            onClick={() => navigate(`/proposals?action=new&company_id=${companyId}`)}
            className="flex-1 sm:flex-none"
          >
            Create Proposal
          </Button>
          <Button variant="secondary" onClick={() => setShowEditForm(true)} className="flex-1 sm:flex-none">
            Edit
          </Button>
          <Button variant="danger" onClick={() => setShowDeleteConfirm(true)} className="flex-1 sm:flex-none">
            Delete
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Tab Content */}
      {activeTab === 'overview' && companyId && (
        <OverviewTab
          company={company}
          contacts={contacts}
          isLoadingContacts={isLoadingContacts}
          companyId={companyId}
        />
      )}

      {activeTab === 'opportunities' && companyId && (
        <OpportunitiesTab companyId={companyId} opportunities={companyOpportunities} />
      )}

      {activeTab === 'contracts' && companyId && (
        <Suspense fallback={<SuspenseFallback />}>
          <ContractsList entityType="company" entityId={companyId} />
        </Suspense>
      )}

      {activeTab === 'quotes' && companyId && (
        <QuotesTab companyId={companyId} quotes={companyQuotes} />
      )}

      {activeTab === 'proposals' && (
        <ProposalsTab proposals={companyProposals} />
      )}

      {activeTab === 'payments' && companyId && (
        <Suspense fallback={<SuspenseFallback />}>
          <EntityPaymentsTab entityType="company" entityId={companyId} />
        </Suspense>
      )}

      {activeTab === 'activities' && companyId && (
        <ActivitiesTab entityType="company" entityId={companyId} />
      )}

      {activeTab === 'meta' && companyId && (
        <Suspense fallback={<SuspenseFallback />}>
          <MetaTab companyId={companyId} />
        </Suspense>
      )}

      {activeTab === 'expenses' && companyId && (
        <Suspense fallback={<SuspenseFallback />}>
          <ExpensesTab companyId={companyId} />
        </Suspense>
      )}

      {companyId && (
        <CommonTabContent
          activeTab={activeTab}
          entityType="companies"
          entityId={companyId}
          enabledTabs={['notes', 'attachments', 'history', 'sharing']}
        />
      )}

      {/* Edit Form Modal */}
      <Modal isOpen={showEditForm} onClose={() => setShowEditForm(false)} title="Edit Company" size="lg">
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

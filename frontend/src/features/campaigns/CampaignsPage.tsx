/**
 * Campaigns list page with status and metrics
 */

import { useState, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import {
  PlusIcon,
  FunnelIcon,
  MegaphoneIcon,
  ChartBarIcon,
  UsersIcon,
  CurrencyDollarIcon,

} from '@heroicons/react/24/outline';
import { showError } from '../../utils/toast';
import { Button, Select, Spinner, Modal, ConfirmDialog } from '../../components/ui';
import { CampaignForm } from './components/CampaignForm';
import { VolumeStats } from './components/VolumeStats';

import {
  useCampaigns,
  useCreateCampaign,
  useUpdateCampaign,
  useDeleteCampaign,
} from '../../hooks/useCampaigns';
import {
  formatCurrency,
  formatDate,
  formatPercentage,
  getStatusColor,
  formatStatusLabel,
} from '../../utils';
import type { Campaign, CampaignCreate, CampaignUpdate, CampaignFilters } from '../../types';

const typeLabels: Record<string, string> = {
  email: 'Email',
  event: 'Event',
  webinar: 'Webinar',
  ads: 'Advertising',
  social: 'Social Media',
  other: 'Other',
};

type SetupStatus = 'needs setup' | 'active' | 'completed';

function getSetupStatus(campaign: Campaign): SetupStatus {
  if (campaign.status === 'completed') return 'completed';
  if (campaign.is_executing || campaign.status === 'active') return 'active';
  if ((campaign.num_sent ?? 0) > 0 || (campaign.num_responses ?? 0) > 0) return 'active';
  return 'needs setup';
}

const setupStatusStyles: Record<SetupStatus, { bg: string; text: string; dot: string }> = {
  'needs setup': {
    bg: 'bg-amber-50 dark:bg-amber-900/20',
    text: 'text-amber-700 dark:text-amber-400',
    dot: 'bg-amber-400',
  },
  active: {
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    text: 'text-blue-700 dark:text-blue-400',
    dot: 'bg-blue-400',
  },
  completed: {
    bg: 'bg-gray-50 dark:bg-gray-700/50',
    text: 'text-gray-600 dark:text-gray-400',
    dot: 'bg-gray-400',
  },
};

const statusOptions = [
  { value: '', label: 'All Status' },
  { value: 'planned', label: 'Planned' },
  { value: 'active', label: 'Active' },
  { value: 'paused', label: 'Paused' },
  { value: 'completed', label: 'Completed' },
];

const typeOptions = [
  { value: '', label: 'All Types' },
  { value: 'email', label: 'Email Campaign' },
  { value: 'event', label: 'Event' },
  { value: 'webinar', label: 'Webinar' },
  { value: 'ads', label: 'Advertising' },
  { value: 'social', label: 'Social Media' },
  { value: 'other', label: 'Other' },
];

function CampaignCard({
  campaign,
  onClick,
  onEdit,
  onDelete,
}: {
  campaign: Campaign;
  onClick: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const statusStyle = getStatusColor(campaign.status, 'campaign');
  const setupStatus = getSetupStatus(campaign);
  const setupStyle = setupStatusStyles[setupStatus];

  return (
    <div
      className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-5 hover:shadow-md transition-shadow cursor-pointer"
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } }}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span
              className={clsx(
                'text-xs font-medium px-2 py-0.5 rounded-full',
                statusStyle.bg,
                statusStyle.text
              )}
            >
              {formatStatusLabel(campaign.status)}
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {typeLabels[campaign.campaign_type] || campaign.campaign_type}
            </span>
            <span
              className={clsx(
                'text-xs font-medium px-2 py-0.5 rounded-full flex items-center gap-1',
                setupStyle.bg,
                setupStyle.text
              )}
            >
              <span className={clsx('inline-block h-1.5 w-1.5 rounded-full flex-shrink-0', setupStyle.dot)} aria-hidden="true" />
              {setupStatus}
            </span>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 truncate">{campaign.name}</h3>
          {campaign.description && (
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">{campaign.description}</p>
          )}
        </div>
        <div className="flex items-center gap-1 ml-4">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onEdit();
            }}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            aria-label="Edit campaign"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
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
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 hover:text-red-500"
            aria-label="Delete campaign"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
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

      {/* Dates */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4 mt-4 text-xs text-gray-500 dark:text-gray-400">
        {campaign.start_date && (
          <span>Start: {formatDate(campaign.start_date, 'long')}</span>
        )}
        {campaign.end_date && (
          <span>End: {formatDate(campaign.end_date, 'long')}</span>
        )}
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
        <div className="text-center">
          <div className="flex items-center justify-center gap-1 text-gray-400 mb-1">
            <UsersIcon className="h-4 w-4" />
          </div>
          <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">{campaign.num_sent}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400">Sent</div>
        </div>
        <div className="text-center">
          <div className="flex items-center justify-center gap-1 text-gray-400 mb-1">
            <ChartBarIcon className="h-4 w-4" />
          </div>
          <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">{campaign.num_responses}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400">Responses</div>
        </div>
        <div className="text-center">
          <div className="flex items-center justify-center gap-1 text-gray-400 mb-1">
            <ChartBarIcon className="h-4 w-4" />
          </div>
          <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {formatPercentage(campaign.response_rate, 1)}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">Response Rate</div>
        </div>
        <div className="text-center">
          <div className="flex items-center justify-center gap-1 text-gray-400 mb-1">
            <CurrencyDollarIcon className="h-4 w-4" />
          </div>
          <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {formatCurrency(campaign.actual_revenue, campaign.budget_currency)}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">Revenue</div>
        </div>
      </div>
    </div>
  );
}

const INITIAL_DELETE_CONFIRM = { isOpen: false, campaign: null } as const;

export function CampaignsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showFilters, setShowFilters] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingCampaign, setEditingCampaign] = useState<Campaign | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; campaign: Campaign | null }>(INITIAL_DELETE_CONFIRM);


  // Get filter values from URL params
  const filters: CampaignFilters = useMemo(
    () => ({
      page: parseInt(searchParams.get('page') || '1', 10),
      page_size: parseInt(searchParams.get('page_size') || '12', 10),
      search: searchParams.get('search') || undefined,
      campaign_type: searchParams.get('campaign_type') || undefined,
      status: searchParams.get('status') || undefined,
    }),
    [searchParams]
  );

  // Fetch campaigns
  const { data: campaignsData, isLoading } = useCampaigns(filters);

  // Mutations
  const createCampaign = useCreateCampaign();
  const updateCampaign = useUpdateCampaign();
  const deleteCampaign = useDeleteCampaign();

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

  const handleDeleteClick = (campaign: Campaign) => {
    setDeleteConfirm({ isOpen: true, campaign });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm.campaign) return;
    try {
      await deleteCampaign.mutateAsync(deleteConfirm.campaign.id);
      setDeleteConfirm(INITIAL_DELETE_CONFIRM);
    } catch (error) {
      showError('Failed to delete campaign');
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm(INITIAL_DELETE_CONFIRM);
  };

  const handleEdit = (campaign: Campaign) => {
    setEditingCampaign(campaign);
    setShowForm(true);
  };

  const handleFormSubmit = async (data: CampaignCreate | CampaignUpdate) => {
    try {
      if (editingCampaign) {
        await updateCampaign.mutateAsync({ id: editingCampaign.id, data: data as CampaignUpdate });
      } else {
        await createCampaign.mutateAsync(data as CampaignCreate);
      }
      setShowForm(false);
      setEditingCampaign(null);
    } catch (error) {
      showError('Failed to save campaign');
    }
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditingCampaign(null);
  };

  const campaigns = campaignsData?.items || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Campaigns</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Manage marketing campaigns and track their performance
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
          <Button
            leftIcon={<PlusIcon className="h-5 w-5" />}
            onClick={() => setShowForm(true)}
            className="w-full sm:w-auto"
          >
            New Campaign
          </Button>
        </div>
      </div>

      {/* Volume Stats Dashboard */}
      <VolumeStats />

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4">
        <Button
          variant="ghost"
          size="sm"
          leftIcon={<FunnelIcon className="h-4 w-4" />}
          onClick={() => setShowFilters(!showFilters)}
          className="w-full sm:w-auto justify-center sm:justify-start"
        >
          Filters
        </Button>

        {campaignsData && (
          <div className="text-sm text-gray-500 dark:text-gray-400 text-center sm:text-right">
            Showing {campaigns.length} of {campaignsData.total} campaigns
          </div>
        )}
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 sm:p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4">
            <Select
              label="Status"
              options={statusOptions}
              value={filters.status || ''}
              onChange={(e) => updateFilter('status', e.target.value)}
            />
            <Select
              label="Type"
              options={typeOptions}
              value={filters.campaign_type || ''}
              onChange={(e) => updateFilter('campaign_type', e.target.value)}
            />
          </div>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : campaigns.length === 0 ? (
        <div className="text-center py-12">
          <MegaphoneIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No campaigns</h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Get started by creating a new campaign.
          </p>
          <div className="mt-6">
            <Button onClick={() => setShowForm(true)}>
              <PlusIcon className="h-5 w-5 mr-2" />
              New Campaign
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {campaigns.map((campaign) => (
              <CampaignCard
                key={campaign.id}
                campaign={campaign}
                onClick={() => navigate(`/campaigns/${campaign.id}`)}
                onEdit={() => handleEdit(campaign)}
                onDelete={() => handleDeleteClick(campaign)}
              />
            ))}
          </div>

          {/* Pagination */}
          {campaignsData && campaignsData.pages > 1 && (
            <div className="flex flex-col sm:flex-row items-center justify-center gap-2 pt-4">
              <div className="flex items-center gap-2 w-full sm:w-auto">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={filters.page === 1}
                  onClick={() => updateFilter('page', String((filters.page || 1) - 1))}
                  className="flex-1 sm:flex-none"
                >
                  Previous
                </Button>
                <span className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
                  Page {filters.page} of {campaignsData.pages}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={filters.page === campaignsData.pages}
                  onClick={() => updateFilter('page', String((filters.page || 1) + 1))}
                  className="flex-1 sm:flex-none"
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Form Modal */}
      <Modal
        isOpen={showForm}
        onClose={handleFormCancel}
        title={editingCampaign ? 'Edit Campaign' : 'New Campaign'}
        size="lg"
      >
        <CampaignForm
          campaign={editingCampaign || undefined}
          onSubmit={handleFormSubmit}
          onCancel={handleFormCancel}
          isLoading={createCampaign.isPending || updateCampaign.isPending}
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete Campaign"
        message={`Are you sure you want to delete "${deleteConfirm.campaign?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteCampaign.isPending}
      />

    </div>
  );
}

export default CampaignsPage;

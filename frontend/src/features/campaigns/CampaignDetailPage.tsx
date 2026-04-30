/**
 * Campaign detail page with members and stats
 */

import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import { useContacts } from '../../hooks/useContacts';
import { useLeads } from '../../hooks/useLeads';
import {
  ArrowLeftIcon,
  PlusIcon,
  UsersIcon,
  ChartBarIcon,
  CurrencyDollarIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import { Button, Spinner, Modal, ConfirmDialog } from '../../components/ui';
import { CampaignForm } from './components/CampaignForm';
import { AddMembersModal } from './components/AddMembersModal';
import { CampaignAnalyticsSection } from './components/CampaignAnalytics';
import {
  useCampaign,
  useCampaignStats,
  useCampaignMembers,
  useUpdateCampaign,
  useDeleteCampaign,
  useRemoveCampaignMember,
  useAddCampaignMembers,
  useCampaignSteps,
  useAddCampaignStep,
  useUpdateCampaignStep,
  useDeleteCampaignStep,
  useExecuteCampaign,
  useEmailTemplates,
} from '../../hooks/useCampaigns';
import { CampaignStepBuilder } from './components/CampaignStepBuilder';
import { getStatusColor, formatStatusLabel } from '../../utils/statusColors';
import { formatCurrency, formatDate } from '../../utils/formatters';
import { showError } from '../../utils/toast';
import type { CampaignUpdate, CampaignMember } from '../../types';

// Member status colors (specific to campaign members, not part of centralized status colors)
const defaultMemberStatusColor = { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-700 dark:text-gray-300' };
const memberStatusColors: Record<string, { bg: string; text: string }> = {
  pending: defaultMemberStatusColor,
  sent: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-400' },
  responded: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-400' },
  converted: { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-700 dark:text-purple-400' },
};

function StatCard({
  icon: Icon,
  label,
  value,
  subValue,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  subValue?: string;
}) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-3 sm:p-4">
      <div className="flex items-center gap-2 sm:gap-3">
        <div className="p-1.5 sm:p-2 bg-gray-100 dark:bg-gray-700 rounded-lg flex-shrink-0">
          <Icon className="h-4 w-4 sm:h-5 sm:w-5 text-gray-600 dark:text-gray-400" />
        </div>
        <div className="min-w-0">
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 truncate">{label}</p>
          <p className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-100">{value}</p>
          {subValue && <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{subValue}</p>}
        </div>
      </div>
    </div>
  );
}

function MemberRow({
  member,
  onRemove,
  contactById,
  leadById,
}: {
  member: CampaignMember;
  onRemove: () => void;
  contactById: Map<number, { full_name: string; email?: string | null }>;
  leadById: Map<number, { full_name: string; email?: string | null }>;
}) {
  const statusStyle = memberStatusColors[member.status] ?? defaultMemberStatusColor;
  const resolved =
    member.member_type === 'contact'
      ? contactById.get(member.member_id)
      : leadById.get(member.member_id);
  const displayName = resolved?.full_name ?? (member.member_type === 'contact' ? `Contact #${member.member_id}` : `Lead #${member.member_id}`);

  return (
    <tr className="hover:bg-gray-50 dark:hover:bg-gray-700">
      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 whitespace-nowrap">
        <span>{displayName}</span>
        {resolved?.email && <span className="block text-xs text-gray-500 dark:text-gray-400">{resolved.email}</span>}
      </td>
      <td className="px-4 py-3">
        <span
          className={clsx(
            'text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap',
            statusStyle.bg,
            statusStyle.text
          )}
        >
          {member.status.charAt(0).toUpperCase() + member.status.slice(1)}
        </span>
      </td>
      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">{formatDate(member.sent_at, 'short')}</td>
      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">{formatDate(member.responded_at, 'short')}</td>
      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">{formatDate(member.converted_at, 'short')}</td>
      <td className="px-4 py-3 text-right">
        <button
          onClick={onRemove}
          className="p-1 text-gray-400 hover:text-red-500 transition-colors"
          title="Remove member"
        >
          <TrashIcon className="h-4 w-4" />
        </button>
      </td>
    </tr>
  );
}

function MemberCard({
  member,
  onRemove,
  contactById,
  leadById,
}: {
  member: CampaignMember;
  onRemove: () => void;
  contactById: Map<number, { full_name: string; email?: string | null }>;
  leadById: Map<number, { full_name: string; email?: string | null }>;
}) {
  const statusStyle = memberStatusColors[member.status] ?? defaultMemberStatusColor;
  const resolved =
    member.member_type === 'contact'
      ? contactById.get(member.member_id)
      : leadById.get(member.member_id);
  const displayName = resolved?.full_name ?? (member.member_type === 'contact' ? `Contact #${member.member_id}` : `Lead #${member.member_id}`);

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="font-medium text-gray-900 dark:text-gray-100 truncate">
            {displayName}
          </p>
          {resolved?.email && <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{resolved.email}</p>}
          <span
            className={clsx(
              'inline-block text-xs font-medium px-2 py-0.5 rounded-full mt-1',
              statusStyle.bg,
              statusStyle.text
            )}
          >
            {member.status.charAt(0).toUpperCase() + member.status.slice(1)}
          </span>
        </div>
        <button
          onClick={onRemove}
          className="p-1.5 text-gray-400 hover:text-red-500 transition-colors flex-shrink-0"
          title="Remove member"
        >
          <TrashIcon className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <div>
          <p className="text-gray-500 dark:text-gray-400">Sent</p>
          <p className="text-gray-900 dark:text-gray-100">{formatDate(member.sent_at, 'short') || '-'}</p>
        </div>
        <div>
          <p className="text-gray-500 dark:text-gray-400">Responded</p>
          <p className="text-gray-900 dark:text-gray-100">{formatDate(member.responded_at, 'short') || '-'}</p>
        </div>
        <div>
          <p className="text-gray-500 dark:text-gray-400">Converted</p>
          <p className="text-gray-900 dark:text-gray-100">{formatDate(member.converted_at, 'short') || '-'}</p>
        </div>
      </div>
    </div>
  );
}

export function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const campaignId = id ? parseInt(id, 10) : undefined;

  const [showEditForm, setShowEditForm] = useState(false);
  const [showAddMembersModal, setShowAddMembersModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [removeMemberConfirm, setRemoveMemberConfirm] = useState<{ isOpen: boolean; memberId: number | null }>({
    isOpen: false,
    memberId: null,
  });

  // Fetch campaign data
  const { data: campaign, isLoading: isLoadingCampaign } = useCampaign(campaignId);
  const { data: stats, isLoading: isLoadingStats } = useCampaignStats(campaignId);
  const { data: members, isLoading: isLoadingMembers } = useCampaignMembers(campaignId);

  // Client-side name resolution: only worth fetching if there's at least
  // one of each member type to look up. Stopgap until the backend joins
  // member name into /campaign-members.
  const hasContactMembers = (members ?? []).some((m) => m.member_type === 'contact');
  const hasLeadMembers = (members ?? []).some((m) => m.member_type === 'lead');
  const { data: contactsData } = useContacts(
    { page_size: 1000 },
    { enabled: hasContactMembers, staleTime: 5 * 60 * 1000 }
  );
  const { data: leadsData } = useLeads(
    { page_size: 1000 },
    { enabled: hasLeadMembers, staleTime: 5 * 60 * 1000 }
  );

  const contactById = useMemo(
    () => new Map((contactsData?.items ?? []).map((c) => [c.id, c] as const)),
    [contactsData]
  );
  const leadById = useMemo(
    () => new Map((leadsData?.items ?? []).map((l) => [l.id, l] as const)),
    [leadsData]
  );

  // Mutations
  const updateCampaign = useUpdateCampaign();
  const deleteCampaign = useDeleteCampaign();
  const removeMember = useRemoveCampaignMember();
  const addMembers = useAddCampaignMembers();
  const addStep = useAddCampaignStep();
  const updateStep = useUpdateCampaignStep();
  const deleteStep = useDeleteCampaignStep();
  const executeCampaign = useExecuteCampaign();

  const { data: steps = [] } = useCampaignSteps(campaignId);
  const { data: templates = [] } = useEmailTemplates();

  // Compute existing member IDs to filter them out in the modal
  const existingMemberIds = useMemo(() => {
    const contacts: number[] = [];
    const leads: number[] = [];
    if (members) {
      members.forEach((m) => {
        if (m.member_type === 'contact') {
          contacts.push(m.member_id);
        } else if (m.member_type === 'lead') {
          leads.push(m.member_id);
        }
      });
    }
    return { contacts, leads };
  }, [members]);

  const handleDeleteConfirm = async () => {
    if (!campaignId) return;
    try {
      await deleteCampaign.mutateAsync(campaignId);
      navigate('/campaigns');
    } catch (error) {
      showError('Failed to delete campaign');
    }
  };

  const handleFormSubmit = async (data: CampaignUpdate) => {
    if (!campaignId) return;
    try {
      await updateCampaign.mutateAsync({ id: campaignId, data });
      setShowEditForm(false);
    } catch (error) {
      showError('Failed to update campaign');
    }
  };

  const handleRemoveMemberClick = (memberId: number) => {
    setRemoveMemberConfirm({ isOpen: true, memberId });
  };

  const handleRemoveMemberConfirm = async () => {
    if (!campaignId || !removeMemberConfirm.memberId) return;
    try {
      await removeMember.mutateAsync({ campaignId, memberId: removeMemberConfirm.memberId });
      setRemoveMemberConfirm({ isOpen: false, memberId: null });
    } catch (error) {
      showError('Failed to remove member');
    }
  };

  const handleAddStep = async (templateId: number, delayDays: number, stepOrder: number) => {
    if (!campaignId) return;
    await addStep.mutateAsync({ campaignId, data: { template_id: templateId, delay_days: delayDays, step_order: stepOrder } });
  };

  const handleUpdateStep = async (stepId: number, data: { delay_days?: number; step_order?: number }) => {
    if (!campaignId) return;
    await updateStep.mutateAsync({ campaignId, stepId, data });
  };

  const handleDeleteStep = async (stepId: number) => {
    if (!campaignId) return;
    await deleteStep.mutateAsync({ campaignId, stepId });
  };

  const handleExecute = async () => {
    if (!campaignId) return;
    try {
      await executeCampaign.mutateAsync(campaignId);
    } catch {
      showError('Failed to start campaign');
    }
  };

  const handleAddMembers = async (memberType: 'contact' | 'lead', memberIds: number[]) => {
    if (!campaignId) return;
    try {
      await addMembers.mutateAsync({
        campaignId,
        data: {
          member_type: memberType,
          member_ids: memberIds,
        },
      });
      setShowAddMembersModal(false);
    } catch (error) {
      showError('Failed to add members');
    }
  };

  const isLoading = isLoadingCampaign || isLoadingStats;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-500 dark:text-gray-400">Campaign not found</p>
        <Button variant="secondary" className="mt-4" onClick={() => navigate('/campaigns')}>
          Back to Campaigns
        </Button>
      </div>
    );
  }

  const statusStyle = getStatusColor(campaign.status, 'campaign');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-start gap-4">
        <button
          onClick={() => navigate('/campaigns')}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors self-start"
        >
          <ArrowLeftIcon className="h-5 w-5 text-gray-500 dark:text-gray-400" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100 break-words">{campaign.name}</h1>
            <span
              className={clsx(
                'text-xs sm:text-sm font-medium px-2 sm:px-3 py-0.5 sm:py-1 rounded-full whitespace-nowrap',
                statusStyle.bg,
                statusStyle.text
              )}
            >
              {formatStatusLabel(campaign.status)}
            </span>
          </div>
          {campaign.description && (
            <p className="text-sm sm:text-base text-gray-600 dark:text-gray-400 mt-1">{campaign.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto">
          {campaign.campaign_type === 'email' && !campaign.is_executing && campaign.status !== 'completed' && (
            <Button
              onClick={handleExecute}
              isLoading={executeCampaign.isPending}
              className="flex-1 sm:flex-none"
            >
              Send Campaign
            </Button>
          )}
          <Button variant="secondary" onClick={() => setShowEditForm(true)} className="flex-1 sm:flex-none">
            Edit
          </Button>
          <Button variant="danger" onClick={() => setShowDeleteConfirm(true)} className="flex-1 sm:flex-none">
            Delete
          </Button>
        </div>
      </div>

      {/* Campaign Details */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-3 sm:p-4">
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">Campaign Type</p>
          <p className="text-base sm:text-lg font-medium text-gray-900 dark:text-gray-100 capitalize">{campaign.campaign_type}</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-3 sm:p-4">
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">Start Date</p>
          <p className="text-base sm:text-lg font-medium text-gray-900 dark:text-gray-100">{formatDate(campaign.start_date, 'long')}</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-3 sm:p-4">
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">End Date</p>
          <p className="text-base sm:text-lg font-medium text-gray-900 dark:text-gray-100">{formatDate(campaign.end_date, 'long')}</p>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-3 sm:p-4">
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">Budget</p>
          <p className="text-base sm:text-lg font-medium text-gray-900 dark:text-gray-100">
            {formatCurrency(campaign.budget_amount, campaign.budget_currency)}
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <StatCard
          icon={UsersIcon}
          label="Total Members"
          value={stats?.total_members || 0}
        />
        <StatCard
          icon={ChartBarIcon}
          label="Response Rate"
          value={stats?.response_rate ? `${stats.response_rate.toFixed(1)}%` : '-'}
          subValue={`${stats?.responded || 0} responses`}
        />
        <StatCard
          icon={ChartBarIcon}
          label="Conversion Rate"
          value={stats?.conversion_rate ? `${stats.conversion_rate.toFixed(1)}%` : '-'}
          subValue={`${stats?.converted || 0} converted`}
        />
        <StatCard
          icon={CurrencyDollarIcon}
          label="Revenue"
          value={formatCurrency(campaign.actual_revenue, campaign.budget_currency)}
          subValue={campaign.roi ? `${campaign.roi.toFixed(1)}% ROI` : undefined}
        />
      </div>

      {/* Funnel Stats */}
      {stats && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
          <h3 className="text-base sm:text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Campaign Funnel</h3>
          {/* Desktop: horizontal funnel */}
          <div className="hidden sm:flex items-center justify-between">
            {[
              { label: 'Pending', value: stats.pending, color: 'bg-gray-200' },
              { label: 'Sent', value: stats.sent, color: 'bg-blue-200' },
              { label: 'Responded', value: stats.responded, color: 'bg-green-200' },
              { label: 'Converted', value: stats.converted, color: 'bg-purple-200' },
            ].map((stage, index) => (
              <div key={stage.label} className="flex-1 flex flex-col items-center">
                <div className="relative w-full flex items-center justify-center">
                  <div
                    className={clsx('w-full h-12 rounded-lg flex items-center justify-center', stage.color)}
                    style={{
                      clipPath: index === 0
                        ? 'polygon(0 0, 90% 0, 100% 50%, 90% 100%, 0 100%)'
                        : index === 3
                          ? 'polygon(10% 0, 100% 0, 100% 100%, 10% 100%, 0 50%)'
                          : 'polygon(10% 0, 90% 0, 100% 50%, 90% 100%, 10% 100%, 0 50%)',
                    }}
                  >
                    <span className="text-lg font-bold text-gray-800 dark:text-gray-200">{stage.value}</span>
                  </div>
                </div>
                <span className="text-sm text-gray-600 dark:text-gray-400 mt-2">{stage.label}</span>
              </div>
            ))}
          </div>
          {/* Mobile: vertical grid */}
          <div className="grid grid-cols-2 gap-3 sm:hidden">
            {[
              { label: 'Pending', value: stats.pending, color: 'bg-gray-200' },
              { label: 'Sent', value: stats.sent, color: 'bg-blue-200' },
              { label: 'Responded', value: stats.responded, color: 'bg-green-200' },
              { label: 'Converted', value: stats.converted, color: 'bg-purple-200' },
            ].map((stage) => (
              <div key={stage.label} className={clsx('rounded-lg p-3 text-center', stage.color)}>
                <span className="text-lg font-bold text-gray-800 dark:text-gray-200 block">{stage.value}</span>
                <span className="text-xs text-gray-600 dark:text-gray-400">{stage.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Campaign Steps */}
      {campaign.campaign_type === 'email' && campaignId && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
          <CampaignStepBuilder
            steps={steps}
            templates={templates}
            onAddStep={handleAddStep}
            onUpdateStep={handleUpdateStep}
            onDeleteStep={handleDeleteStep}
            isLoading={addStep.isPending || updateStep.isPending || deleteStep.isPending}
          />
        </div>
      )}

      {/* Email Analytics */}
      {campaign.campaign_type === 'email' && campaignId && (
        <div>
          <h3 className="text-base sm:text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">Email Analytics</h3>
          <CampaignAnalyticsSection campaignId={campaignId} />
        </div>
      )}

      {/* Members */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="px-4 sm:px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h3 className="text-base sm:text-lg font-semibold text-gray-900 dark:text-gray-100">Campaign Members</h3>
          <Button
            size="sm"
            leftIcon={<PlusIcon className="h-4 w-4" />}
            onClick={() => setShowAddMembersModal(true)}
            className="w-full sm:w-auto"
          >
            Add Members
          </Button>
        </div>
        {isLoadingMembers ? (
          <div className="flex items-center justify-center py-12">
            <Spinner />
          </div>
        ) : !members || members.length === 0 ? (
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            <UsersIcon className="mx-auto h-12 w-12 text-gray-400 mb-2" />
            <p>No members in this campaign yet</p>
          </div>
        ) : (
          <>
            {/* Mobile: Card view */}
            <div className="sm:hidden p-4 space-y-3">
              {members.map((member) => (
                <MemberCard
                  key={member.id}
                  member={member}
                  onRemove={() => handleRemoveMemberClick(member.id)}
                  contactById={contactById}
                  leadById={leadById}
                />
              ))}
            </div>
            {/* Desktop: Table view */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-900">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                      Member
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                      Sent
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                      Responded
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                      Converted
                    </th>
                    <th className="px-4 py-3"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                  {members.map((member) => (
                    <MemberRow
                      key={member.id}
                      member={member}
                      onRemove={() => handleRemoveMemberClick(member.id)}
                      contactById={contactById}
                      leadById={leadById}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>

      {/* Edit Form Modal */}
      <Modal
        isOpen={showEditForm}
        onClose={() => setShowEditForm(false)}
        title="Edit Campaign"
        size="lg"
      >
        <CampaignForm
          campaign={campaign}
          onSubmit={handleFormSubmit}
          onCancel={() => setShowEditForm(false)}
          isLoading={updateCampaign.isPending}
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDeleteConfirm}
        title="Delete Campaign"
        message={`Are you sure you want to delete "${campaign.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteCampaign.isPending}
      />

      {/* Remove Member Confirmation Dialog */}
      <ConfirmDialog
        isOpen={removeMemberConfirm.isOpen}
        onClose={() => setRemoveMemberConfirm({ isOpen: false, memberId: null })}
        onConfirm={handleRemoveMemberConfirm}
        title="Remove Member"
        message="Are you sure you want to remove this member from the campaign?"
        confirmLabel="Remove"
        cancelLabel="Cancel"
        variant="warning"
        isLoading={removeMember.isPending}
      />

      {/* Add Members Modal */}
      {showAddMembersModal && campaignId && (
        <AddMembersModal
          campaignId={campaignId}
          existingMemberIds={existingMemberIds}
          onClose={() => setShowAddMembersModal(false)}
          onAdd={handleAddMembers}
          isLoading={addMembers.isPending}
        />
      )}
    </div>
  );
}

export default CampaignDetailPage;

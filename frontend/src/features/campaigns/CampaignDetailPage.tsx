/**
 * Campaign detail page with members and stats
 */

import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
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
import {
  useCampaign,
  useCampaignStats,
  useCampaignMembers,
  useUpdateCampaign,
  useDeleteCampaign,
  useRemoveCampaignMember,
  useAddCampaignMembers,
} from '../../hooks/useCampaigns';
import { getStatusColor, formatStatusLabel } from '../../utils/statusColors';
import { formatCurrency, formatDate } from '../../utils/formatters';
import type { CampaignUpdate, CampaignMember } from '../../types';

// Member status colors (specific to campaign members, not part of centralized status colors)
const defaultMemberStatusColor = { bg: 'bg-gray-100', text: 'text-gray-700' };
const memberStatusColors: Record<string, { bg: string; text: string }> = {
  pending: defaultMemberStatusColor,
  sent: { bg: 'bg-blue-100', text: 'text-blue-700' },
  responded: { bg: 'bg-green-100', text: 'text-green-700' },
  converted: { bg: 'bg-purple-100', text: 'text-purple-700' },
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
    <div className="bg-white rounded-lg shadow-sm border p-3 sm:p-4">
      <div className="flex items-center gap-2 sm:gap-3">
        <div className="p-1.5 sm:p-2 bg-gray-100 rounded-lg flex-shrink-0">
          <Icon className="h-4 w-4 sm:h-5 sm:w-5 text-gray-600" />
        </div>
        <div className="min-w-0">
          <p className="text-xs sm:text-sm text-gray-500 truncate">{label}</p>
          <p className="text-lg sm:text-xl font-semibold text-gray-900">{value}</p>
          {subValue && <p className="text-xs text-gray-500 truncate">{subValue}</p>}
        </div>
      </div>
    </div>
  );
}

function MemberRow({
  member,
  onRemove,
}: {
  member: CampaignMember;
  onRemove: () => void;
}) {
  const statusStyle = memberStatusColors[member.status] ?? defaultMemberStatusColor;

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-3 text-sm text-gray-900 whitespace-nowrap">
        {member.member_type === 'contact' ? 'Contact' : 'Lead'} #{member.member_id}
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
      <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">{formatDate(member.sent_at, 'short')}</td>
      <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">{formatDate(member.responded_at, 'short')}</td>
      <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">{formatDate(member.converted_at, 'short')}</td>
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
}: {
  member: CampaignMember;
  onRemove: () => void;
}) {
  const statusStyle = memberStatusColors[member.status] ?? defaultMemberStatusColor;

  return (
    <div className="bg-white border rounded-lg p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="font-medium text-gray-900 truncate">
            {member.member_type === 'contact' ? 'Contact' : 'Lead'} #{member.member_id}
          </p>
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
          <p className="text-gray-500">Sent</p>
          <p className="text-gray-900">{formatDate(member.sent_at, 'short') || '-'}</p>
        </div>
        <div>
          <p className="text-gray-500">Responded</p>
          <p className="text-gray-900">{formatDate(member.responded_at, 'short') || '-'}</p>
        </div>
        <div>
          <p className="text-gray-500">Converted</p>
          <p className="text-gray-900">{formatDate(member.converted_at, 'short') || '-'}</p>
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

  // Mutations
  const updateCampaign = useUpdateCampaign();
  const deleteCampaign = useDeleteCampaign();
  const removeMember = useRemoveCampaignMember();
  const addMembers = useAddCampaignMembers();

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
      console.error('Failed to delete campaign:', error);
    }
  };

  const handleFormSubmit = async (data: CampaignUpdate) => {
    if (!campaignId) return;
    try {
      await updateCampaign.mutateAsync({ id: campaignId, data });
      setShowEditForm(false);
    } catch (error) {
      console.error('Failed to update campaign:', error);
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
      console.error('Failed to remove member:', error);
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
      console.error('Failed to add members:', error);
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
        <p className="text-gray-500">Campaign not found</p>
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
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors self-start"
        >
          <ArrowLeftIcon className="h-5 w-5 text-gray-500" />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <h1 className="text-xl sm:text-2xl font-bold text-gray-900 break-words">{campaign.name}</h1>
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
            <p className="text-sm sm:text-base text-gray-600 mt-1">{campaign.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto">
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
        <div className="bg-white rounded-lg shadow-sm border p-3 sm:p-4">
          <p className="text-xs sm:text-sm text-gray-500">Campaign Type</p>
          <p className="text-base sm:text-lg font-medium text-gray-900 capitalize">{campaign.campaign_type}</p>
        </div>
        <div className="bg-white rounded-lg shadow-sm border p-3 sm:p-4">
          <p className="text-xs sm:text-sm text-gray-500">Start Date</p>
          <p className="text-base sm:text-lg font-medium text-gray-900">{formatDate(campaign.start_date, 'long')}</p>
        </div>
        <div className="bg-white rounded-lg shadow-sm border p-3 sm:p-4">
          <p className="text-xs sm:text-sm text-gray-500">End Date</p>
          <p className="text-base sm:text-lg font-medium text-gray-900">{formatDate(campaign.end_date, 'long')}</p>
        </div>
        <div className="bg-white rounded-lg shadow-sm border p-3 sm:p-4">
          <p className="text-xs sm:text-sm text-gray-500">Budget</p>
          <p className="text-base sm:text-lg font-medium text-gray-900">
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
        <div className="bg-white rounded-lg shadow-sm border p-4 sm:p-6">
          <h3 className="text-base sm:text-lg font-semibold text-gray-900 mb-4">Campaign Funnel</h3>
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
                    <span className="text-lg font-bold text-gray-800">{stage.value}</span>
                  </div>
                </div>
                <span className="text-sm text-gray-600 mt-2">{stage.label}</span>
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
                <span className="text-lg font-bold text-gray-800 block">{stage.value}</span>
                <span className="text-xs text-gray-600">{stage.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Members */}
      <div className="bg-white rounded-lg shadow-sm border">
        <div className="px-4 sm:px-6 py-4 border-b flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h3 className="text-base sm:text-lg font-semibold text-gray-900">Campaign Members</h3>
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
          <div className="text-center py-12 text-gray-500">
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
                />
              ))}
            </div>
            {/* Desktop: Table view */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Member
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Sent
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Responded
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                      Converted
                    </th>
                    <th className="px-4 py-3"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {members.map((member) => (
                    <MemberRow
                      key={member.id}
                      member={member}
                      onRemove={() => handleRemoveMemberClick(member.id)}
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

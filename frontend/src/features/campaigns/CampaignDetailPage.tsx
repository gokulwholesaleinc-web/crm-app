/**
 * Campaign detail page with members and stats
 */

import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import clsx from 'clsx';
import {
  ArrowLeftIcon,
  PlusIcon,
  UsersIcon,
  ChartBarIcon,
  CurrencyDollarIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { CampaignForm } from './components/CampaignForm';
import {
  useCampaign,
  useCampaignStats,
  useCampaignMembers,
  useUpdateCampaign,
  useDeleteCampaign,
  useRemoveCampaignMember,
} from '../../hooks/useCampaigns';
import type { CampaignUpdate, CampaignMember } from '../../types';

const defaultStatusColor = { bg: 'bg-gray-100', text: 'text-gray-700' };

const statusColors: Record<string, { bg: string; text: string }> = {
  planned: defaultStatusColor,
  active: { bg: 'bg-green-100', text: 'text-green-700' },
  paused: { bg: 'bg-yellow-100', text: 'text-yellow-700' },
  completed: { bg: 'bg-blue-100', text: 'text-blue-700' },
};

const defaultMemberStatusColor = { bg: 'bg-gray-100', text: 'text-gray-700' };

const memberStatusColors: Record<string, { bg: string; text: string }> = {
  pending: defaultMemberStatusColor,
  sent: { bg: 'bg-blue-100', text: 'text-blue-700' },
  responded: { bg: 'bg-green-100', text: 'text-green-700' },
  converted: { bg: 'bg-purple-100', text: 'text-purple-700' },
};

function formatCurrency(amount: number | null | undefined, currency = 'USD'): string {
  if (amount === null || amount === undefined) return '-';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

function formatDate(date: string | null | undefined): string {
  if (!date) return '-';
  try {
    return format(new Date(date), 'MMM d, yyyy');
  } catch {
    return date;
  }
}

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
    <div className="bg-white rounded-lg shadow-sm border p-4">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-gray-100 rounded-lg">
          <Icon className="h-5 w-5 text-gray-600" />
        </div>
        <div>
          <p className="text-sm text-gray-500">{label}</p>
          <p className="text-xl font-semibold text-gray-900">{value}</p>
          {subValue && <p className="text-xs text-gray-500">{subValue}</p>}
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
      <td className="px-4 py-3 text-sm text-gray-900">
        {member.member_type === 'contact' ? 'Contact' : 'Lead'} #{member.member_id}
      </td>
      <td className="px-4 py-3">
        <span
          className={clsx(
            'text-xs font-medium px-2 py-0.5 rounded-full',
            statusStyle.bg,
            statusStyle.text
          )}
        >
          {member.status.charAt(0).toUpperCase() + member.status.slice(1)}
        </span>
      </td>
      <td className="px-4 py-3 text-sm text-gray-500">{formatDate(member.sent_at)}</td>
      <td className="px-4 py-3 text-sm text-gray-500">{formatDate(member.responded_at)}</td>
      <td className="px-4 py-3 text-sm text-gray-500">{formatDate(member.converted_at)}</td>
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

export function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const campaignId = id ? parseInt(id, 10) : undefined;

  const [showEditForm, setShowEditForm] = useState(false);

  // Fetch campaign data
  const { data: campaign, isLoading: isLoadingCampaign } = useCampaign(campaignId);
  const { data: stats, isLoading: isLoadingStats } = useCampaignStats(campaignId);
  const { data: members, isLoading: isLoadingMembers } = useCampaignMembers(campaignId);

  // Mutations
  const updateCampaign = useUpdateCampaign();
  const deleteCampaign = useDeleteCampaign();
  const removeMember = useRemoveCampaignMember();

  const handleDelete = async () => {
    if (!campaignId) return;
    if (!window.confirm('Are you sure you want to delete this campaign?')) return;
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

  const handleRemoveMember = async (memberId: number) => {
    if (!campaignId) return;
    if (!window.confirm('Remove this member from the campaign?')) return;
    try {
      await removeMember.mutateAsync({ campaignId, memberId });
    } catch (error) {
      console.error('Failed to remove member:', error);
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

  const statusStyle = statusColors[campaign.status] ?? defaultStatusColor;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/campaigns')}
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
        >
          <ArrowLeftIcon className="h-5 w-5 text-gray-500" />
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">{campaign.name}</h1>
            <span
              className={clsx(
                'text-sm font-medium px-3 py-1 rounded-full',
                statusStyle.bg,
                statusStyle.text
              )}
            >
              {campaign.status.charAt(0).toUpperCase() + campaign.status.slice(1)}
            </span>
          </div>
          {campaign.description && (
            <p className="text-gray-600 mt-1">{campaign.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => setShowEditForm(true)}>
            Edit
          </Button>
          <Button variant="danger" onClick={handleDelete}>
            Delete
          </Button>
        </div>
      </div>

      {/* Campaign Details */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow-sm border p-4">
          <p className="text-sm text-gray-500">Campaign Type</p>
          <p className="text-lg font-medium text-gray-900 capitalize">{campaign.campaign_type}</p>
        </div>
        <div className="bg-white rounded-lg shadow-sm border p-4">
          <p className="text-sm text-gray-500">Start Date</p>
          <p className="text-lg font-medium text-gray-900">{formatDate(campaign.start_date)}</p>
        </div>
        <div className="bg-white rounded-lg shadow-sm border p-4">
          <p className="text-sm text-gray-500">End Date</p>
          <p className="text-lg font-medium text-gray-900">{formatDate(campaign.end_date)}</p>
        </div>
        <div className="bg-white rounded-lg shadow-sm border p-4">
          <p className="text-sm text-gray-500">Budget</p>
          <p className="text-lg font-medium text-gray-900">
            {formatCurrency(campaign.budget_amount, campaign.budget_currency)}
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
        <div className="bg-white rounded-lg shadow-sm border p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Campaign Funnel</h3>
          <div className="flex items-center justify-between">
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
        </div>
      )}

      {/* Members */}
      <div className="bg-white rounded-lg shadow-sm border">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">Campaign Members</h3>
          <Button size="sm" leftIcon={<PlusIcon className="h-4 w-4" />}>
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
          <div className="overflow-x-auto">
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
                    onRemove={() => handleRemoveMember(member.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Edit Form Modal */}
      {showEditForm && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-screen items-center justify-center p-4">
            <div
              className="fixed inset-0 bg-black bg-opacity-25"
              onClick={() => setShowEditForm(false)}
            />
            <div className="relative bg-white rounded-lg shadow-xl max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Edit Campaign</h2>
              <CampaignForm
                campaign={campaign}
                onSubmit={handleFormSubmit}
                onCancel={() => setShowEditForm(false)}
                isLoading={updateCampaign.isPending}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CampaignDetailPage;

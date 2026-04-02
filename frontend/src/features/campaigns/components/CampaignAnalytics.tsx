/**
 * Campaign email analytics: summary cards + per-step metrics table with bar visualization.
 */

import {
  EnvelopeIcon,
  EnvelopeOpenIcon,
  CursorArrowRaysIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { Spinner } from '../../../components/ui';
import { useCampaignAnalytics } from '../../../hooks/useCampaigns';
import type { StepAnalytics } from '../../../types';

function AnalyticCard({
  icon: Icon,
  label,
  value,
  rate,
  color,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  rate?: string;
  color: string;
}) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-3 sm:p-4">
      <div className="flex items-center gap-2 sm:gap-3">
        <div className={`p-1.5 sm:p-2 rounded-lg flex-shrink-0 ${color}`}>
          <Icon className="h-4 w-4 sm:h-5 sm:w-5 text-white" />
        </div>
        <div className="min-w-0">
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 truncate">{label}</p>
          <p className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-gray-100">{value}</p>
          {rate && <p className="text-xs text-gray-500 dark:text-gray-400">{rate}</p>}
        </div>
      </div>
    </div>
  );
}

function RateBar({ rate, color }: { rate: number; color: string }) {
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="flex-1 h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${Math.min(rate, 100)}%` }}
        />
      </div>
      <span className="text-xs font-medium text-gray-600 dark:text-gray-400 w-12 text-right flex-shrink-0">
        {rate}%
      </span>
    </div>
  );
}

function StepRow({ step }: { step: StepAnalytics }) {
  return (
    <tr className="hover:bg-gray-50 dark:hover:bg-gray-700">
      <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap">
        {step.step_order + 1}
      </td>
      <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100 whitespace-nowrap">
        {step.template_name}
      </td>
      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 text-right whitespace-nowrap">
        {step.sent}
      </td>
      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 text-right whitespace-nowrap">
        {step.opened}
      </td>
      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 text-right whitespace-nowrap">
        {step.clicked}
      </td>
      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 text-right whitespace-nowrap">
        {step.failed}
      </td>
      <td className="px-4 py-3 min-w-[120px]">
        <RateBar rate={step.open_rate} color="bg-blue-500" />
      </td>
      <td className="px-4 py-3 min-w-[120px]">
        <RateBar rate={step.click_rate} color="bg-green-500" />
      </td>
    </tr>
  );
}

function StepCard({ step }: { step: StepAnalytics }) {
  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
          Step {step.step_order + 1}: {step.template_name}
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3 text-xs mb-3">
        <div>
          <p className="text-gray-500 dark:text-gray-400">Sent</p>
          <p className="font-medium text-gray-900 dark:text-gray-100">{step.sent}</p>
        </div>
        <div>
          <p className="text-gray-500 dark:text-gray-400">Opened</p>
          <p className="font-medium text-gray-900 dark:text-gray-100">{step.opened}</p>
        </div>
        <div>
          <p className="text-gray-500 dark:text-gray-400">Clicked</p>
          <p className="font-medium text-gray-900 dark:text-gray-100">{step.clicked}</p>
        </div>
        <div>
          <p className="text-gray-500 dark:text-gray-400">Failed</p>
          <p className="font-medium text-gray-900 dark:text-gray-100">{step.failed}</p>
        </div>
      </div>
      <div className="space-y-2">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Open Rate</p>
          <RateBar rate={step.open_rate} color="bg-blue-500" />
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Click Rate</p>
          <RateBar rate={step.click_rate} color="bg-green-500" />
        </div>
      </div>
    </div>
  );
}

export function CampaignAnalyticsSection({ campaignId }: { campaignId: number }) {
  const { data: analytics, isLoading } = useCampaignAnalytics(campaignId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner />
      </div>
    );
  }

  if (!analytics) {
    return null;
  }

  const bounceRate = analytics.total_sent > 0
    ? round((analytics.total_failed / analytics.total_sent) * 100, 1)
    : 0;

  return (
    <div className="space-y-4">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <AnalyticCard
          icon={EnvelopeIcon}
          label="Total Sent"
          value={analytics.total_sent}
          color="bg-gray-500"
        />
        <AnalyticCard
          icon={EnvelopeOpenIcon}
          label="Open Rate"
          value={analytics.total_opened}
          rate={`${analytics.open_rate}%`}
          color="bg-blue-500"
        />
        <AnalyticCard
          icon={CursorArrowRaysIcon}
          label="Click Rate"
          value={analytics.total_clicked}
          rate={`${analytics.click_rate}%`}
          color="bg-green-500"
        />
        <AnalyticCard
          icon={ExclamationTriangleIcon}
          label="Bounce Rate"
          value={analytics.total_failed}
          rate={`${bounceRate}%`}
          color="bg-red-500"
        />
      </div>

      {/* Per-Step Table */}
      {analytics.steps.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
          <div className="px-4 sm:px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <h3 className="text-base sm:text-lg font-semibold text-gray-900 dark:text-gray-100">
              Per-Step Metrics
            </h3>
          </div>

          {/* Mobile: Card view */}
          <div className="sm:hidden p-4 space-y-3">
            {analytics.steps.map((step) => (
              <StepCard key={step.step_order} step={step} />
            ))}
          </div>

          {/* Desktop: Table view */}
          <div className="hidden sm:block overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-900">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Step
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Template
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Sent
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Opened
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Clicked
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Failed
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Open Rate
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                    Click Rate
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {analytics.steps.map((step) => (
                  <StepRow key={step.step_order} step={step} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {analytics.steps.length === 0 && analytics.total_sent === 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
          <EnvelopeIcon className="mx-auto h-12 w-12 text-gray-400 mb-2" />
          <p className="text-gray-500 dark:text-gray-400">No email data yet. Execute the campaign to see analytics.</p>
        </div>
      )}
    </div>
  );
}

function round(value: number, decimals: number): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

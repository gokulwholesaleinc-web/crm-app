/**
 * Email settings section for Settings page.
 * Manages daily send limit, email warmup configuration, and warmup schedule preview.
 */

import { useState, useEffect, useMemo } from 'react';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import {
  useEmailSettings,
  useUpdateEmailSettings,
} from '../../../hooks/useCampaigns';
import {
  EnvelopeIcon,
  FireIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';

function generateWarmupSchedule(targetDaily: number): { label: string; limit: number }[] {
  const schedule: { label: string; limit: number }[] = [];
  let current = 20;
  let day = 1;
  while (current < targetDaily) {
    const endDay = day + 2;
    schedule.push({ label: `Day ${day}-${endDay}`, limit: current });
    day = endDay + 1;
    current = Math.min(current * 2, targetDaily);
  }
  schedule.push({ label: `Day ${day}+`, limit: targetDaily });
  return schedule;
}

export function EmailSettingsSection() {
  const { data: settings, isLoading } = useEmailSettings();
  const updateSettings = useUpdateEmailSettings();

  const [dailyLimit, setDailyLimit] = useState(200);
  const [warmupEnabled, setWarmupEnabled] = useState(false);
  const [warmupStartDate, setWarmupStartDate] = useState('');
  const [warmupTarget, setWarmupTarget] = useState(200);
  const [isDirty, setIsDirty] = useState(false);

  useEffect(() => {
    if (settings) {
      setDailyLimit(settings.daily_send_limit);
      setWarmupEnabled(settings.warmup_enabled);
      setWarmupStartDate(settings.warmup_start_date || '');
      setWarmupTarget(settings.warmup_target_daily);
      setIsDirty(false);
    }
  }, [settings]);

  const warmupSchedule = useMemo(
    () => warmupEnabled ? generateWarmupSchedule(warmupTarget) : [],
    [warmupEnabled, warmupTarget]
  );

  const handleSave = async () => {
    try {
      await updateSettings.mutateAsync({
        daily_send_limit: dailyLimit,
        warmup_enabled: warmupEnabled,
        warmup_start_date: warmupEnabled && warmupStartDate ? warmupStartDate : null,
        warmup_target_daily: warmupTarget,
      });
      toast.success('Email settings saved');
      setIsDirty(false);
    } catch {
      toast.error('Failed to save email settings');
    }
  };

  const markDirty = () => setIsDirty(true);

  if (isLoading) {
    return (
      <Card>
        <CardHeader title="Email Settings" description="Configure email sending limits and warmup" />
        <CardBody className="p-4 sm:p-6">
          <div className="flex items-center justify-center py-4">
            <Spinner size="sm" />
          </div>
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Email Settings"
        description="Configure daily send limits and email warmup"
        action={
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!isDirty}
            isLoading={updateSettings.isPending}
          >
            Save
          </Button>
        }
      />
      <CardBody className="p-4 sm:p-6">
        <div className="space-y-6">
          {/* Daily Send Limit */}
          <div>
            <label htmlFor="daily-send-limit" className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              <EnvelopeIcon className="h-4 w-4 text-gray-400" aria-hidden="true" />
              Daily Send Limit
            </label>
            <input
              id="daily-send-limit"
              type="number"
              min={1}
              max={10000}
              value={dailyLimit}
              onChange={(e) => { setDailyLimit(Math.max(1, parseInt(e.target.value, 10) || 1)); markDirty(); }}
              className="block w-40 rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Maximum number of emails to send per day
            </p>
          </div>

          {/* Warmup Toggle */}
          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={warmupEnabled}
                onChange={(e) => { setWarmupEnabled(e.target.checked); markDirty(); }}
                className="rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
              />
              <div className="flex items-center gap-2">
                <FireIcon className="h-4 w-4 text-orange-500" aria-hidden="true" />
                <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  Enable Email Warmup
                </span>
              </div>
            </label>
            <p className="mt-1 ml-8 text-xs text-gray-500 dark:text-gray-400">
              Gradually increase sending volume to build sender reputation
            </p>
          </div>

          {/* Warmup Configuration */}
          {warmupEnabled && (
            <div className="ml-8 space-y-4 p-4 bg-orange-50 dark:bg-orange-900/10 rounded-lg border border-orange-200 dark:border-orange-800">
              <div>
                <label htmlFor="warmup-start-date" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Warmup Start Date
                </label>
                <input
                  id="warmup-start-date"
                  type="date"
                  value={warmupStartDate}
                  onChange={(e) => { setWarmupStartDate(e.target.value); markDirty(); }}
                  className="block w-48 rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
                />
              </div>

              <div>
                <label htmlFor="warmup-target" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Target Daily Limit
                </label>
                <input
                  id="warmup-target"
                  type="number"
                  min={20}
                  max={10000}
                  value={warmupTarget}
                  onChange={(e) => { setWarmupTarget(Math.max(20, parseInt(e.target.value, 10) || 20)); markDirty(); }}
                  className="block w-40 rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
                />
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  The daily send limit after warmup completes
                </p>
              </div>

              {/* Warmup Schedule Preview */}
              {warmupSchedule.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Warmup Schedule Preview
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {warmupSchedule.map((step) => (
                      <div
                        key={step.label}
                        className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-300"
                      >
                        <span className="font-medium">{step.label}:</span>
                        <span>{step.limit}/day</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </CardBody>
    </Card>
  );
}

export default EmailSettingsSection;

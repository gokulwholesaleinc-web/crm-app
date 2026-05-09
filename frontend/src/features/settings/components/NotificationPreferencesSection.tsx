/**
 * Notification preferences section. Lets the user toggle the in-app and
 * email channels globally, pick an email digest cadence, opt out of
 * specific event types per-channel, and define a quiet-hours window.
 *
 * The event matrix is opt-out: if the server does not send a row for a
 * given event, both channels are treated as ON. Saving only sends the
 * fields the user touched (partial PUT).
 */

import { useEffect, useState } from 'react';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import { useUnsavedChangesWarning } from '../../../hooks/useUnsavedChangesWarning';
import {
  useNotificationPrefs,
  useUpdateNotificationPrefs,
} from '../../../hooks/useAccount';
import {
  NOTIFICATION_EVENT_TYPES,
  type EmailDigest,
  type EventChannelPrefs,
  type NotificationPrefs,
} from '../../../api/account';
import { showError } from '../../../utils/toast';

type Channel = 'in_app' | 'email';

const DIGEST_OPTIONS: ReadonlyArray<{ value: EmailDigest; label: string; hint: string }> = [
  { value: 'instant', label: 'Instant', hint: 'Send each notification email as it happens.' },
  { value: 'daily_8am', label: 'Daily digest (8am)', hint: 'One email a day summarizing everything.' },
  { value: 'off', label: 'Off', hint: 'No email notifications, even if individual events are on.' },
];

function isChannelEnabled(matrix: Record<string, EventChannelPrefs>, eventKey: string, channel: Channel): boolean {
  // Opt-out: only OFF when the server explicitly says false.
  return matrix[eventKey]?.[channel] !== false;
}

function withChannelToggle(
  matrix: Record<string, EventChannelPrefs>,
  eventKey: string,
  channel: Channel,
  next: boolean,
): Record<string, EventChannelPrefs> {
  const existing = matrix[eventKey] ?? {};
  return { ...matrix, [eventKey]: { ...existing, [channel]: next } };
}

export function NotificationPreferencesSection() {
  const { data, isLoading, isError } = useNotificationPrefs();
  const updatePrefs = useUpdateNotificationPrefs();

  const [inAppEnabled, setInAppEnabled] = useState(true);
  const [emailEnabled, setEmailEnabled] = useState(true);
  const [emailDigest, setEmailDigest] = useState<EmailDigest>('instant');
  const [quietEnabled, setQuietEnabled] = useState(false);
  const [quietStart, setQuietStart] = useState('22:00');
  const [quietEnd, setQuietEnd] = useState('07:00');
  const [matrix, setMatrix] = useState<Record<string, EventChannelPrefs>>({});
  const [isDirty, setIsDirty] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');

  useEffect(() => {
    if (!data) return;
    setInAppEnabled(data.in_app_enabled);
    setEmailEnabled(data.email_enabled);
    setEmailDigest(data.email_digest);
    setQuietEnabled(data.quiet_hours_enabled);
    setQuietStart(data.quiet_hours_start ?? '22:00');
    setQuietEnd(data.quiet_hours_end ?? '07:00');
    setMatrix(data.event_matrix ?? {});
    setIsDirty(false);
  }, [data]);

  useUnsavedChangesWarning(isDirty);

  const markDirty = () => setIsDirty(true);

  const handleSave = async () => {
    setStatusMessage('Saving…');
    const payload: Partial<NotificationPrefs> = {
      in_app_enabled: inAppEnabled,
      email_enabled: emailEnabled,
      email_digest: emailDigest,
      quiet_hours_enabled: quietEnabled,
      quiet_hours_start: quietEnabled ? quietStart : null,
      quiet_hours_end: quietEnabled ? quietEnd : null,
      event_matrix: matrix,
    };
    try {
      await updatePrefs.mutateAsync(payload);
      setIsDirty(false);
      setStatusMessage('Saved');
    } catch {
      setStatusMessage('Failed to save');
      showError('Failed to save notification preferences');
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader title="Notifications" description="Choose how the CRM tells you about activity" />
        <CardBody className="p-4 sm:p-6">
          <div className="flex items-center justify-center py-4">
            <Spinner size="sm" />
          </div>
        </CardBody>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardHeader title="Notifications" description="Choose how the CRM tells you about activity" />
        <CardBody className="p-4 sm:p-6">
          <p className="text-sm text-red-600 dark:text-red-400">
            Could not load notification preferences. Refresh to try again.
          </p>
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Notifications"
        description="Choose how the CRM tells you about activity"
      />
      <CardBody className="p-4 sm:p-6">
        <div className="space-y-6">
          {/* Channels */}
          <fieldset>
            <legend className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Channels
            </legend>
            <div className="mt-2 space-y-2">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  id="notif-in-app-master"
                  type="checkbox"
                  checked={inAppEnabled}
                  onChange={(e) => { setInAppEnabled(e.target.checked); markDirty(); }}
                  className="rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                />
                <span className="text-sm text-gray-900 dark:text-gray-100">
                  In-app notifications
                </span>
              </label>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  id="notif-email-master"
                  type="checkbox"
                  checked={emailEnabled}
                  onChange={(e) => { setEmailEnabled(e.target.checked); markDirty(); }}
                  className="rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                />
                <span className="text-sm text-gray-900 dark:text-gray-100">
                  Email notifications
                </span>
              </label>
            </div>
          </fieldset>

          {/* Email digest — hidden when email is off */}
          {emailEnabled && (
            <fieldset className="border-t border-gray-200 dark:border-gray-700 pt-4">
              <legend className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                Email digest
              </legend>
              <div className="mt-2 space-y-2">
                {DIGEST_OPTIONS.map((opt) => {
                  const id = `notif-digest-${opt.value}`;
                  return (
                    <label key={opt.value} htmlFor={id} className="flex items-start gap-3 cursor-pointer">
                      <input
                        id={id}
                        type="radio"
                        name="notif-digest"
                        value={opt.value}
                        checked={emailDigest === opt.value}
                        onChange={() => { setEmailDigest(opt.value); markDirty(); }}
                        className="mt-0.5 border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                      />
                      <span className="text-sm text-gray-900 dark:text-gray-100">
                        <span className="font-medium">{opt.label}</span>
                        <span className="block text-xs text-gray-500 dark:text-gray-400">
                          {opt.hint}
                        </span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          )}

          {/* Event matrix */}
          <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Event preferences
            </h4>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Turn off individual events you don't want to be told about.
            </p>
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full text-sm">
                <caption className="sr-only">
                  Per-event notification channels. Each event can be toggled on or off for in-app and email channels.
                </caption>
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th scope="col" className="text-left font-medium text-gray-700 dark:text-gray-300 py-2 pr-4">
                      Event
                    </th>
                    <th scope="col" className="text-center font-medium text-gray-700 dark:text-gray-300 py-2 px-3 w-24">
                      In-app
                    </th>
                    <th scope="col" className="text-center font-medium text-gray-700 dark:text-gray-300 py-2 px-3 w-24">
                      Email
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {NOTIFICATION_EVENT_TYPES.map((event) => {
                    const inAppChecked = isChannelEnabled(matrix, event.key, 'in_app');
                    const emailChecked = isChannelEnabled(matrix, event.key, 'email');
                    const inAppId = `notif-${event.key}-in_app`;
                    const emailId = `notif-${event.key}-email`;
                    return (
                      <tr key={event.key} className="border-b border-gray-100 dark:border-gray-800 last:border-0">
                        <td className="py-2 pr-4">
                          <span className="text-gray-900 dark:text-gray-100">{event.label}</span>
                        </td>
                        <td className="py-2 px-3 text-center">
                          <label htmlFor={inAppId} className="inline-flex items-center justify-center cursor-pointer">
                            <span className="sr-only">{`${event.label}: in-app`}</span>
                            <input
                              id={inAppId}
                              type="checkbox"
                              checked={inAppChecked}
                              onChange={(e) => {
                                setMatrix((curr) => withChannelToggle(curr, event.key, 'in_app', e.target.checked));
                                markDirty();
                              }}
                              className="rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                            />
                          </label>
                        </td>
                        <td className="py-2 px-3 text-center">
                          <label htmlFor={emailId} className="inline-flex items-center justify-center cursor-pointer">
                            <span className="sr-only">{`${event.label}: email`}</span>
                            <input
                              id={emailId}
                              type="checkbox"
                              checked={emailChecked}
                              onChange={(e) => {
                                setMatrix((curr) => withChannelToggle(curr, event.key, 'email', e.target.checked));
                                markDirty();
                              }}
                              className="rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                            />
                          </label>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Quiet hours */}
          <fieldset className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <legend className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Quiet hours
            </legend>
            <label className="mt-2 flex items-center gap-3 cursor-pointer">
              <input
                id="notif-quiet-toggle"
                type="checkbox"
                checked={quietEnabled}
                onChange={(e) => { setQuietEnabled(e.target.checked); markDirty(); }}
                className="rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
              />
              <span className="text-sm text-gray-900 dark:text-gray-100">
                Suppress non-urgent notifications during these hours
              </span>
            </label>
            {quietEnabled && (
              <div className="mt-3 ml-7 flex flex-wrap items-center gap-3">
                <div>
                  <label htmlFor="notif-quiet-start" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                    From
                  </label>
                  <input
                    id="notif-quiet-start"
                    type="time"
                    value={quietStart}
                    onChange={(e) => { setQuietStart(e.target.value); markDirty(); }}
                    className="rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
                  />
                </div>
                <div>
                  <label htmlFor="notif-quiet-end" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                    To
                  </label>
                  <input
                    id="notif-quiet-end"
                    type="time"
                    value={quietEnd}
                    onChange={(e) => { setQuietEnd(e.target.value); markDirty(); }}
                    className="rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
                  />
                </div>
              </div>
            )}
          </fieldset>

          {/* Save */}
          <div className="border-t border-gray-200 dark:border-gray-700 pt-4 flex items-center gap-3">
            <Button
              onClick={handleSave}
              disabled={!isDirty || updatePrefs.isPending}
              isLoading={updatePrefs.isPending}
            >
              Save changes
            </Button>
            <span aria-live="polite" className="text-xs text-gray-500 dark:text-gray-400">
              {statusMessage}
            </span>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

export default NotificationPreferencesSection;

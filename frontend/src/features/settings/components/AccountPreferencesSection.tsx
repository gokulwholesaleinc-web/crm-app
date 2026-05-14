/**
 * Display preferences section: timezone, locale, formats, theme, and the
 * landing page that opens after sign-in. Server is the source of truth so
 * preferences follow the user across browsers — local-only mirroring is
 * not in scope here.
 */

import { useEffect, useMemo, useState } from 'react';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import { useUnsavedChangesWarning } from '../../../hooks/useUnsavedChangesWarning';
import {
  useAccountPreferences,
  useUpdateAccountPreferences,
} from '../../../hooks/useAccount';
import type {
  AccountPreferences,
  CurrencyDisplay,
  DateFormat,
  DefaultLanding,
  Locale,
  Theme,
  TimeFormat,
  WeekStart,
} from '../../../api/account';
import { showError } from '../../../utils/toast';

const DEFAULT_TIMEZONE = 'America/Chicago';

const DEFAULTS: AccountPreferences = {
  timezone: DEFAULT_TIMEZONE,
  locale: 'en-US',
  date_format: 'MM/DD/YYYY',
  time_format: '12h',
  week_start: 'sunday',
  currency_display: 'USD',
  theme: 'system',
  default_landing: '/dashboard',
};

const LOCALE_OPTIONS: ReadonlyArray<{ value: Locale; label: string }> = [
  { value: 'en-US', label: 'English (United States)' },
  { value: 'en-GB', label: 'English (United Kingdom)' },
  { value: 'es-MX', label: 'Español (México)' },
];

const DATE_FORMAT_OPTIONS: ReadonlyArray<{ value: DateFormat; label: string; example: string }> = [
  { value: 'MM/DD/YYYY', label: 'MM/DD/YYYY', example: '05/07/2026' },
  { value: 'DD/MM/YYYY', label: 'DD/MM/YYYY', example: '07/05/2026' },
  { value: 'YYYY-MM-DD', label: 'YYYY-MM-DD', example: '2026-05-07' },
];

const TIME_FORMAT_OPTIONS: ReadonlyArray<{ value: TimeFormat; label: string }> = [
  { value: '12h', label: '12-hour (3:45 PM)' },
  { value: '24h', label: '24-hour (15:45)' },
];

const WEEK_START_OPTIONS: ReadonlyArray<{ value: WeekStart; label: string }> = [
  { value: 'sunday', label: 'Sunday' },
  { value: 'monday', label: 'Monday' },
];

const CURRENCY_OPTIONS: ReadonlyArray<{ value: CurrencyDisplay; label: string }> = [
  { value: 'USD', label: 'USD ($)' },
  { value: 'EUR', label: 'EUR (€)' },
  { value: 'GBP', label: 'GBP (£)' },
  { value: 'CAD', label: 'CAD (C$)' },
];

const THEME_OPTIONS: ReadonlyArray<{ value: Theme; label: string }> = [
  { value: 'system', label: 'Match system' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

const LANDING_OPTIONS: ReadonlyArray<{ value: DefaultLanding; label: string }> = [
  { value: '/dashboard', label: 'Dashboard' },
  { value: '/leads', label: 'Leads' },
  { value: '/contacts', label: 'Contacts' },
  { value: '/proposals', label: 'Proposals' },
  { value: '/contracts', label: 'Contracts' },
];

function getSupportedTimeZones(): string[] {
  // Intl.supportedValuesOf is widely supported (Chrome 99+, Safari 15.4+,
  // Firefox 93+); fall back to a single-entry list so the select still
  // renders an option in ancient runtimes (jsdom included).
  type IntlWithSupportedValues = typeof Intl & {
    supportedValuesOf?: (key: string) => string[];
  };
  const intl = Intl as IntlWithSupportedValues;
  if (typeof intl.supportedValuesOf === 'function') {
    try {
      const zones = intl.supportedValuesOf('timeZone');
      if (zones.length > 0) return zones;
    } catch {
      // fallthrough
    }
  }
  return [DEFAULT_TIMEZONE, 'UTC', 'America/New_York', 'America/Los_Angeles', 'Europe/London'];
}

export function AccountPreferencesSection() {
  const { data, isLoading, isError } = useAccountPreferences();
  const updatePrefs = useUpdateAccountPreferences();

  const [prefs, setPrefs] = useState<AccountPreferences>(DEFAULTS);
  const [isDirty, setIsDirty] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');

  useEffect(() => {
    if (!data) return;
    setPrefs(data);
    setIsDirty(false);
  }, [data]);

  useUnsavedChangesWarning(isDirty);

  const timeZones = useMemo(() => getSupportedTimeZones(), []);

  const setField = <K extends keyof AccountPreferences>(key: K, value: AccountPreferences[K]) => {
    setPrefs((curr) => ({ ...curr, [key]: value }));
    setIsDirty(true);
  };

  const handleSave = async () => {
    setStatusMessage('Saving…');
    try {
      await updatePrefs.mutateAsync(prefs);
      setIsDirty(false);
      setStatusMessage('Saved');
    } catch {
      setStatusMessage('Failed to save');
      showError('Failed to save preferences');
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader title="Preferences" description="Localization, display, and defaults" />
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
        <CardHeader title="Preferences" description="Localization, display, and defaults" />
        <CardBody className="p-4 sm:p-6">
          <p className="text-sm text-red-600 dark:text-red-400">
            Could not load preferences. Refresh to try again.
          </p>
        </CardBody>
      </Card>
    );
  }

  const inputClass =
    'block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm';

  return (
    <Card>
      <CardHeader
        title="Preferences"
        description="Localization, display, and defaults"
      />
      <CardBody className="p-4 sm:p-6">
        <div className="space-y-6">
          {/* Localization */}
          <fieldset>
            <legend className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Localization
            </legend>
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="prefs-timezone" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                  Time zone
                </label>
                <select
                  id="prefs-timezone"
                  value={prefs.timezone}
                  onChange={(e) => setField('timezone', e.target.value)}
                  className={inputClass}
                >
                  {timeZones.map((tz) => (
                    <option key={tz} value={tz}>{tz}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="prefs-locale" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                  Language &amp; region
                </label>
                <select
                  id="prefs-locale"
                  value={prefs.locale}
                  onChange={(e) => setField('locale', e.target.value as Locale)}
                  className={inputClass}
                >
                  {LOCALE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            </div>
          </fieldset>

          {/* Display */}
          <fieldset className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <legend className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Display
            </legend>

            <div className="mt-3 space-y-4">
              <div>
                <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">Date format</p>
                <div className="space-y-2">
                  {DATE_FORMAT_OPTIONS.map((opt) => {
                    const id = `prefs-date-${opt.value}`;
                    return (
                      <label key={opt.value} htmlFor={id} className="flex items-center gap-3 cursor-pointer">
                        <input
                          id={id}
                          type="radio"
                          name="prefs-date-format"
                          value={opt.value}
                          checked={prefs.date_format === opt.value}
                          onChange={() => setField('date_format', opt.value)}
                          className="border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                        />
                        <span className="text-sm text-gray-900 dark:text-gray-100">
                          {opt.label} <span className="text-xs text-gray-500 dark:text-gray-400">({opt.example})</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>

              <div>
                <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">Time format</p>
                <div className="space-y-2">
                  {TIME_FORMAT_OPTIONS.map((opt) => {
                    const id = `prefs-time-${opt.value}`;
                    return (
                      <label key={opt.value} htmlFor={id} className="flex items-center gap-3 cursor-pointer">
                        <input
                          id={id}
                          type="radio"
                          name="prefs-time-format"
                          value={opt.value}
                          checked={prefs.time_format === opt.value}
                          onChange={() => setField('time_format', opt.value)}
                          className="border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                        />
                        <span className="text-sm text-gray-900 dark:text-gray-100">{opt.label}</span>
                      </label>
                    );
                  })}
                </div>
              </div>

              <div>
                <p className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-2">Week starts on</p>
                <div className="space-y-2">
                  {WEEK_START_OPTIONS.map((opt) => {
                    const id = `prefs-week-${opt.value}`;
                    return (
                      <label key={opt.value} htmlFor={id} className="flex items-center gap-3 cursor-pointer">
                        <input
                          id={id}
                          type="radio"
                          name="prefs-week-start"
                          value={opt.value}
                          checked={prefs.week_start === opt.value}
                          onChange={() => setField('week_start', opt.value)}
                          className="border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                        />
                        <span className="text-sm text-gray-900 dark:text-gray-100">{opt.label}</span>
                      </label>
                    );
                  })}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="prefs-currency" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                    Currency display
                  </label>
                  <select
                    id="prefs-currency"
                    value={prefs.currency_display}
                    onChange={(e) => setField('currency_display', e.target.value as CurrencyDisplay)}
                    className={inputClass}
                  >
                    {CURRENCY_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="prefs-theme" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                    Theme
                  </label>
                  <select
                    id="prefs-theme"
                    value={prefs.theme}
                    onChange={(e) => setField('theme', e.target.value as Theme)}
                    className={inputClass}
                  >
                    {THEME_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          </fieldset>

          {/* Defaults */}
          <fieldset className="border-t border-gray-200 dark:border-gray-700 pt-4">
            <legend className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Defaults
            </legend>
            <div className="mt-3">
              <label htmlFor="prefs-landing" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                Landing page after sign-in
              </label>
              <select
                id="prefs-landing"
                value={prefs.default_landing}
                onChange={(e) => setField('default_landing', e.target.value as DefaultLanding)}
                className={`${inputClass} sm:max-w-xs`}
              >
                {LANDING_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
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

export default AccountPreferencesSection;

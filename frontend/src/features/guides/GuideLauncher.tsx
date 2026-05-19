import { Fragment } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Menu, Transition } from '@headlessui/react';
import {
  AcademicCapIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  NoSymbolIcon,
  QuestionMarkCircleIcon,
} from '@heroicons/react/24/outline';
import clsx from 'clsx';
import { useGuides } from './GuideProvider';
import type { Guide } from './guideContent';

function GuideMenuItem({
  guide,
  completed,
  onStart,
}: {
  guide: Guide;
  completed: boolean;
  onStart: () => void;
}) {
  return (
    <Menu.Item>
      {({ active }) => (
        <button
          type="button"
          onClick={onStart}
          className={clsx(
            'flex w-full items-start gap-3 px-4 py-3 text-left text-sm touch-manipulation',
            active
              ? 'bg-gray-100 text-gray-900 dark:bg-gray-700 dark:text-gray-100'
              : 'text-gray-700 dark:text-gray-300',
          )}
        >
          <span
            className={clsx(
              'mt-0.5 inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg',
              completed
                ? 'bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-300'
                : 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-300',
            )}
          >
            {completed ? (
              <CheckCircleIcon className="h-4 w-4" aria-hidden="true" />
            ) : (
              <AcademicCapIcon className="h-4 w-4" aria-hidden="true" />
            )}
          </span>
          <span className="min-w-0">
            <span className="block font-medium">{completed ? `Restart ${guide.title}` : guide.title}</span>
            <span className="mt-0.5 block text-xs text-gray-500 dark:text-gray-400">
              {guide.description}
            </span>
            <span className="mt-1 inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-300">
              {getStepSummary(guide.steps.length)}
            </span>
          </span>
        </button>
      )}
    </Menu.Item>
  );
}

function getLauncherPageLabel(pathname: string): string {
  const segment = pathname.split('/').filter(Boolean)[0];
  if (!segment) return 'Dashboard';
  return segment
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function getGuideSummary(count: number): string {
  return `${count} ${count === 1 ? 'guide' : 'guides'}`;
}

function getStepSummary(count: number): string {
  return `${count} ${count === 1 ? 'step' : 'steps'}`;
}

export function GuideLauncher() {
  const {
    availableGuides,
    currentPageGuides,
    recommendedGuides,
    guidesDisabled,
    isCompleted,
    startGuide,
    setGuidesEnabled,
    resetProgress,
  } = useGuides();
  const location = useLocation();
  const currentGuide = currentPageGuides[0];
  // Only fall back to role recommendations when the user is on a context
  // where those tours are actually relevant — the dashboard root. On a
  // feature page that has no dedicated tour (e.g. /companies), the
  // recommended list would surface admin-tool tours like
  // "Restart User approvals" or "Admin dashboard" that have nothing to
  // do with the page; let the empty state direct them to /help instead.
  const onDashboard = location.pathname === '/' || location.pathname === '';
  const menuGuides =
    currentPageGuides.length > 0
      ? currentPageGuides
      : onDashboard
        ? recommendedGuides.slice(0, 4)
        : [];
  const pageLabel = getLauncherPageLabel(location.pathname);
  const completedCount = availableGuides.filter((guide) => isCompleted(guide.id)).length;
  const launcherLabel = guidesDisabled
    ? 'Guides off'
    : currentGuide
      ? 'Page guide'
      : onDashboard
        ? 'Guides'
        : 'Help guides';
  const launcherTitle = guidesDisabled
    ? 'Guides are disabled'
    : currentGuide
      ? `Open ${currentGuide.title} guide for ${pageLabel}`
      : `Open guides for ${pageLabel}`;
  const menuDescription = guidesDisabled
    ? 'Guides are disabled for your account.'
    : currentGuide
      ? `${currentGuide.title} is available for ${pageLabel}.`
      : menuGuides.length > 0
        ? `${getGuideSummary(menuGuides.length)} recommended from your role.`
        : `No guide is tied to ${pageLabel} yet. Help has every role-relevant tour.`;

  return (
    <Menu as="div" className="relative" data-guide="header-guide">
      <Menu.Button
        className={clsx(
          'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 touch-manipulation',
          guidesDisabled
            ? 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:text-gray-500 dark:hover:bg-gray-700 dark:hover:text-gray-300'
            : 'text-primary-700 hover:bg-primary-50 dark:text-primary-300 dark:hover:bg-primary-900/20',
        )}
        aria-label={launcherTitle}
        title={launcherTitle}
      >
        {guidesDisabled ? (
          <NoSymbolIcon className="h-5 w-5" aria-hidden="true" />
        ) : (
          <AcademicCapIcon className="h-5 w-5" aria-hidden="true" />
        )}
        <span className="hidden lg:inline">{launcherLabel}</span>
      </Menu.Button>
      <Transition
        as={Fragment}
        enter="transition ease-out duration-100"
        enterFrom="transform opacity-0 scale-95"
        enterTo="transform opacity-100 scale-100"
        leave="transition ease-in duration-75"
        leaveFrom="transform opacity-100 scale-100"
        leaveTo="transform opacity-0 scale-95"
      >
        <Menu.Items className="absolute right-0 z-50 mt-2 w-80 origin-top-right rounded-lg bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus-visible:outline-none dark:bg-gray-800 dark:ring-gray-700">
          <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                  {currentGuide ? `${pageLabel} guide` : 'Interactive guides'}
                </p>
                <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                  {menuDescription}
                </p>
              </div>
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                {completedCount}/{availableGuides.length}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
              {guidesDisabled
                ? 'Re-enable guides to run page tours again.'
                : currentGuide
                  ? 'Start the current page tour, then browse Help for role-specific refreshers.'
                  : 'Completion count is scoped to guides available for your role.'}
            </p>
          </div>

          {guidesDisabled ? (
            <Menu.Item>
              {({ active }) => (
                <button
                  type="button"
                  onClick={() => setGuidesEnabled(true)}
                  className={clsx(
                    'flex w-full items-center gap-3 px-4 py-3 text-sm touch-manipulation',
                    active ? 'bg-gray-100 text-gray-900 dark:bg-gray-700 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300',
                  )}
                >
                  <AcademicCapIcon className="h-5 w-5 text-primary-500" aria-hidden="true" />
                  Enable guides
                </button>
              )}
            </Menu.Item>
          ) : (
            menuGuides.map((guide) => (
              <GuideMenuItem
                key={guide.id}
                guide={guide}
                completed={isCompleted(guide.id)}
                onStart={() => startGuide(guide.id)}
              />
            ))
          )}

          <div className="border-t border-gray-100 dark:border-gray-700" />
          <Menu.Item>
            {({ active }) => (
              <button
                type="button"
                onClick={resetProgress}
                className={clsx(
                  'flex w-full items-center gap-3 px-4 py-3 text-sm touch-manipulation',
                  active ? 'bg-gray-100 text-gray-900 dark:bg-gray-700 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300',
                )}
              >
                <ArrowPathIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
                Reset guide progress
              </button>
            )}
          </Menu.Item>
          {!guidesDisabled && (
            <Menu.Item>
              {({ active }) => (
                <button
                  type="button"
                  onClick={() => setGuidesEnabled(false)}
                  className={clsx(
                    'flex w-full items-center gap-3 px-4 py-3 text-sm touch-manipulation',
                    active ? 'bg-gray-100 text-gray-900 dark:bg-gray-700 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300',
                  )}
                >
                  <NoSymbolIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
                  Disable guides
                </button>
              )}
            </Menu.Item>
          )}
          <Menu.Item>
            {({ active }) => (
              <Link
                to="/help"
                className={clsx(
                  'flex items-center gap-3 px-4 py-3 text-sm touch-manipulation',
                  active ? 'bg-gray-100 text-gray-900 dark:bg-gray-700 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300',
                )}
              >
                <QuestionMarkCircleIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
                Browse all guides in Help
              </Link>
            )}
          </Menu.Item>
        </Menu.Items>
      </Transition>
    </Menu>
  );
}

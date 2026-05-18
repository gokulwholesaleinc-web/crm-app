import { Fragment } from 'react';
import { Link } from 'react-router-dom';
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
          {completed ? (
            <CheckCircleIcon className="mt-0.5 h-5 w-5 flex-shrink-0 text-green-500" aria-hidden="true" />
          ) : (
            <AcademicCapIcon className="mt-0.5 h-5 w-5 flex-shrink-0 text-primary-500" aria-hidden="true" />
          )}
          <span className="min-w-0">
            <span className="block font-medium">{completed ? `Restart ${guide.title}` : guide.title}</span>
            <span className="mt-0.5 block text-xs text-gray-500 dark:text-gray-400">
              {guide.description}
            </span>
          </span>
        </button>
      )}
    </Menu.Item>
  );
}

export function GuideLauncher() {
  const {
    currentPageGuides,
    recommendedGuides,
    guidesDisabled,
    isCompleted,
    startGuide,
    setGuidesEnabled,
    resetProgress,
  } = useGuides();
  const currentGuide = currentPageGuides[0];
  const menuGuides = currentPageGuides.length > 0 ? currentPageGuides : recommendedGuides.slice(0, 4);

  return (
    <Menu as="div" className="relative" data-guide="header-guide">
      <Menu.Button
        className={clsx(
          'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 touch-manipulation',
          guidesDisabled
            ? 'text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:text-gray-500 dark:hover:bg-gray-700 dark:hover:text-gray-300'
            : 'text-primary-700 hover:bg-primary-50 dark:text-primary-300 dark:hover:bg-primary-900/20',
        )}
        aria-label="Open guide menu"
        title="Guide"
      >
        {guidesDisabled ? (
          <NoSymbolIcon className="h-5 w-5" aria-hidden="true" />
        ) : (
          <AcademicCapIcon className="h-5 w-5" aria-hidden="true" />
        )}
        <span className="hidden lg:inline">Guide</span>
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
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Interactive guides
            </p>
            <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
              {guidesDisabled
                ? 'Guides are disabled for your account.'
                : currentGuide
                  ? 'Start the current page tour or pick a recommended refresher.'
                  : 'Pick a recommended tour or browse all guides in Help.'}
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

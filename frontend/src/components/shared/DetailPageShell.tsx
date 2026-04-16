import { lazy, Suspense } from 'react';
import { Spinner } from '../ui/Spinner';
import { useTimeline } from '../../hooks/useActivities';
import { formatDate } from '../../utils/formatters';
import clsx from 'clsx';

const NotesList = lazy(() => import('./NotesList'));
const AttachmentList = lazy(() => import('./AttachmentList'));
const AuditTimeline = lazy(() => import('./AuditTimeline'));
const SharePanel = lazy(() => import('./SharePanel'));
const CommentSection = lazy(() => import('./CommentSection'));

export function SuspenseFallback() {
  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 animate-pulse">
      <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/3 mb-4" />
      <div className="space-y-3">
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded" />
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-5/6" />
      </div>
    </div>
  );
}

export interface TabDef<T extends string> {
  id: T;
  name: string;
}

interface TabBarProps<T extends string> {
  tabs: TabDef<T>[];
  activeTab: T;
  onTabChange: (tab: T) => void;
}

export function TabBar<T extends string>({ tabs, activeTab, onTabChange }: TabBarProps<T>) {
  return (
    <div className="border-b border-gray-200 dark:border-gray-700 overflow-x-auto">
      <nav className="-mb-px flex space-x-4 sm:space-x-8 min-w-max px-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={clsx(
              'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex-shrink-0',
              activeTab === tab.id
                ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
            )}
          >
            {tab.name}
          </button>
        ))}
      </nav>
    </div>
  );
}

interface ActivitiesTabProps {
  entityType: string;
  entityId: number;
}

export function ActivitiesTab({ entityType, entityId }: ActivitiesTabProps) {
  const { data: timelineData, isLoading } = useTimeline(entityType, entityId);
  const activities = timelineData?.items || [];

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
      <div className="px-4 py-5 sm:p-6">
        {isLoading ? (
          <div className="flex items-center justify-center py-4">
            <Spinner />
          </div>
        ) : activities.length === 0 ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
            No activities recorded yet.
          </p>
        ) : (
          <ul className="space-y-4">
            {activities.map((activity) => (
              <li
                key={activity.id}
                className="flex items-start space-x-3 pb-4 border-b border-gray-100 dark:border-gray-700 last:border-0"
              >
                <div className="flex-shrink-0">
                  <div className="h-8 w-8 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center">
                    <svg
                      className="h-4 w-4 text-primary-600 dark:text-primary-400"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      aria-hidden="true"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-900 dark:text-gray-100">{activity.subject}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {formatDate(activity.created_at)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

type CommonTab = 'notes' | 'attachments' | 'history' | 'sharing' | 'comments';

interface CommonTabContentProps {
  activeTab: string;
  entityType: string;
  entityId: number;
  enabledTabs?: CommonTab[];
}

const DEFAULT_TABS: CommonTab[] = ['notes', 'attachments', 'history', 'sharing'];

export function CommonTabContent({
  activeTab,
  entityType,
  entityId,
  enabledTabs = DEFAULT_TABS,
}: CommonTabContentProps) {
  const enabled = new Set(enabledTabs);

  return (
    <>
      {enabled.has('notes') && activeTab === 'notes' && (
        <Suspense fallback={<SuspenseFallback />}>
          <NotesList entityType={entityType} entityId={entityId} />
        </Suspense>
      )}

      {enabled.has('attachments') && activeTab === 'attachments' && (
        <Suspense fallback={<SuspenseFallback />}>
          <AttachmentList entityType={entityType} entityId={entityId} />
        </Suspense>
      )}

      {enabled.has('comments') && activeTab === 'comments' && (
        <Suspense fallback={<SuspenseFallback />}>
          <CommentSection entityType={entityType} entityId={entityId} />
        </Suspense>
      )}

      {enabled.has('history') && activeTab === 'history' && (
        <Suspense fallback={<SuspenseFallback />}>
          <AuditTimeline entityType={entityType} entityId={entityId} />
        </Suspense>
      )}

      {enabled.has('sharing') && activeTab === 'sharing' && (
        <Suspense fallback={<SuspenseFallback />}>
          <SharePanel entityType={entityType} entityId={entityId} />
        </Suspense>
      )}
    </>
  );
}

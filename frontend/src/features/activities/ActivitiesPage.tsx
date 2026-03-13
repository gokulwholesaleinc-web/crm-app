/**
 * Activities list/timeline view with filters by type
 */

import { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import clsx from 'clsx';
import {
  PlusIcon,
  FunnelIcon,
  ListBulletIcon,
  ClockIcon,
  PhoneIcon,
  EnvelopeIcon,
  CalendarIcon,
  ClipboardDocumentCheckIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';
import { Button, Select, Spinner, Modal, ConfirmDialog } from '../../components/ui';
import { ActivityCard } from './components/ActivityCard';
import { ActivityTimeline } from './components/ActivityTimeline';
import { ActivityForm } from './components/ActivityForm';
import CalendarView from './components/CalendarView';
import {
  useActivities,
  useUserTimeline,
  useCreateActivity,
  useUpdateActivity,
  useDeleteActivity,
  useCompleteActivity,
} from '../../hooks/useActivities';
import { showError } from '../../utils/toast';
import type { Activity, ActivityCreate, ActivityUpdate, ActivityFilters } from '../../types';

type ViewMode = 'list' | 'timeline' | 'calendar';

const activityTypeIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  call: PhoneIcon,
  email: EnvelopeIcon,
  meeting: CalendarIcon,
  task: ClipboardDocumentCheckIcon,
  note: DocumentTextIcon,
};

const priorityBadgeClasses: Record<string, string> = {
  low: 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300',
  normal: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300',
  high: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300',
  urgent: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300',
};

const activityTypeFilters = [
  { value: '', label: 'All Types', icon: null },
  { value: 'call', label: 'Calls', icon: PhoneIcon },
  { value: 'email', label: 'Emails', icon: EnvelopeIcon },
  { value: 'meeting', label: 'Meetings', icon: CalendarIcon },
  { value: 'task', label: 'Tasks', icon: ClipboardDocumentCheckIcon },
  { value: 'note', label: 'Notes', icon: DocumentTextIcon },
];

const priorityOptions = [
  { value: '', label: 'All Priorities' },
  { value: 'low', label: 'Low' },
  { value: 'normal', label: 'Normal' },
  { value: 'high', label: 'High' },
  { value: 'urgent', label: 'Urgent' },
];

const statusOptions = [
  { value: '', label: 'All Status' },
  { value: 'pending', label: 'Pending' },
  { value: 'completed', label: 'Completed' },
];

const INITIAL_DELETE_CONFIRM = { isOpen: false, activity: null } as const;

export function ActivitiesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [showFilters, setShowFilters] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingActivity, setEditingActivity] = useState<Activity | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; activity: Activity | null }>(INITIAL_DELETE_CONFIRM);

  // Get filter values from URL params
  const filters: ActivityFilters = useMemo(
    () => ({
      page: parseInt(searchParams.get('page') || '1', 10),
      page_size: parseInt(searchParams.get('page_size') || '20', 10),
      activity_type: searchParams.get('activity_type') || undefined,
      priority: searchParams.get('priority') || undefined,
      is_completed:
        searchParams.get('status') === 'completed'
          ? true
          : searchParams.get('status') === 'pending'
            ? false
            : undefined,
    }),
    [searchParams]
  );

  // Fetch activities - only fetch the active view's data
  const { data: activitiesData, isLoading: isLoadingList } = useActivities(
    filters,
    { enabled: viewMode !== 'timeline' }
  );
  const { data: timelineData, isLoading: isLoadingTimeline } = useUserTimeline(
    filters.activity_type,
    { enabled: viewMode === 'timeline' }
  );

  // Mutations
  const createActivity = useCreateActivity();
  const updateActivity = useUpdateActivity();
  const deleteActivity = useDeleteActivity();
  const completeActivity = useCompleteActivity();

  const updateFilter = (key: string, value: string) => {
    const newParams = new URLSearchParams(searchParams);
    if (value) {
      newParams.set(key, value);
    } else {
      newParams.delete(key);
    }
    // Reset to page 1 when filters change
    if (key !== 'page') {
      newParams.set('page', '1');
    }
    setSearchParams(newParams);
  };

  const handleComplete = async (id: number) => {
    try {
      await completeActivity.mutateAsync({ id });
    } catch (error) {
      showError('Failed to complete activity');
    }
  };

  const handleDeleteClick = (activity: Activity) => {
    setDeleteConfirm({ isOpen: true, activity });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm.activity) return;
    try {
      await deleteActivity.mutateAsync(deleteConfirm.activity.id);
      setDeleteConfirm(INITIAL_DELETE_CONFIRM);
    } catch (error) {
      showError('Failed to delete activity');
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm(INITIAL_DELETE_CONFIRM);
  };

  const handleEdit = (activity: Activity) => {
    setEditingActivity(activity);
    setShowForm(true);
  };

  const handleFormSubmit = async (data: ActivityCreate | ActivityUpdate) => {
    try {
      if (editingActivity) {
        await updateActivity.mutateAsync({ id: editingActivity.id, data: data as ActivityUpdate });
      } else {
        await createActivity.mutateAsync(data as ActivityCreate);
      }
      setShowForm(false);
      setEditingActivity(null);
    } catch (error) {
      showError('Failed to save activity');
    }
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditingActivity(null);
  };

  const isLoading = viewMode === 'list' ? isLoadingList : viewMode === 'timeline' ? isLoadingTimeline : false;
  const activities = activitiesData?.items || [];
  const timelineItems = timelineData?.items || [];

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Activities</h1>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 mt-1">
            Track and manage all your activities in one place
          </p>
        </div>
        <Button
          leftIcon={<PlusIcon className="h-4 w-4 sm:h-5 sm:w-5" />}
          onClick={() => setShowForm(true)}
          className="w-full sm:w-auto"
        >
          New Activity
        </Button>
      </div>

      {/* Activity Type Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700 -mx-4 px-4 sm:mx-0 sm:px-0 overflow-x-auto">
        <nav className="flex -mb-px space-x-3 sm:space-x-6 min-w-max" aria-label="Activity types">
          {activityTypeFilters.map((type) => {
            const Icon = type.icon;
            const isActive =
              (type.value === '' && !filters.activity_type) ||
              type.value === filters.activity_type;
            return (
              <button
                key={type.value}
                onClick={() => updateFilter('activity_type', type.value)}
                className={clsx(
                  'flex items-center gap-1.5 sm:gap-2 py-2.5 sm:py-3 px-1 border-b-2 text-xs sm:text-sm font-medium transition-colors whitespace-nowrap',
                  isActive
                    ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                    : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
                )}
              >
                {Icon && <Icon className="h-3.5 w-3.5 sm:h-4 sm:w-4" />}
                <span className="hidden xs:inline sm:inline">{type.label}</span>
                <span className="xs:hidden sm:hidden">{type.label.slice(0, 4)}</span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Toolbar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center justify-between sm:justify-start gap-2">
          <div className="flex items-center gap-1 sm:gap-2">
            <button
              onClick={() => setViewMode('list')}
              className={clsx(
                'p-2 sm:p-2 rounded-lg transition-colors',
                viewMode === 'list'
                  ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400'
                  : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-600 dark:hover:text-gray-300'
              )}
              aria-label="List view"
            >
              <ListBulletIcon className="h-5 w-5" aria-hidden="true" />
            </button>
            <button
              onClick={() => setViewMode('timeline')}
              className={clsx(
                'p-2 sm:p-2 rounded-lg transition-colors',
                viewMode === 'timeline'
                  ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400'
                  : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-600 dark:hover:text-gray-300'
              )}
              aria-label="Timeline view"
            >
              <ClockIcon className="h-5 w-5" aria-hidden="true" />
            </button>
            <button
              onClick={() => setViewMode('calendar')}
              className={clsx(
                'p-2 sm:p-2 rounded-lg transition-colors',
                viewMode === 'calendar'
                  ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-600 dark:text-primary-400'
                  : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-600 dark:hover:text-gray-300'
              )}
              aria-label="Calendar view"
            >
              <CalendarIcon className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<FunnelIcon className="h-4 w-4" />}
            onClick={() => setShowFilters(!showFilters)}
            className="ml-1 sm:ml-2"
          >
            <span className="hidden sm:inline">Filters</span>
            <span className="sm:hidden">Filter</span>
          </Button>
        </div>

        {viewMode === 'list' && activitiesData && (
          <div className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 text-center sm:text-right">
            Showing {activities.length} of {activitiesData.total} activities
          </div>
        )}
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 sm:p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4">
            <Select
              label="Priority"
              options={priorityOptions}
              value={filters.priority || ''}
              onChange={(e) => updateFilter('priority', e.target.value)}
            />
            <Select
              label="Status"
              options={statusOptions}
              value={
                filters.is_completed === true
                  ? 'completed'
                  : filters.is_completed === false
                    ? 'pending'
                    : ''
              }
              onChange={(e) => updateFilter('status', e.target.value)}
            />
          </div>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-8 sm:py-12">
          <Spinner size="lg" />
        </div>
      ) : viewMode === 'list' ? (
        <div className="space-y-3 sm:space-y-4">
          {activities.length === 0 ? (
            <div className="text-center py-8 sm:py-12">
              <DocumentTextIcon className="mx-auto h-10 w-10 sm:h-12 sm:w-12 text-gray-400" />
              <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No activities</h3>
              <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
                Get started by creating a new activity.
              </p>
              <div className="mt-4 sm:mt-6">
                <Button onClick={() => setShowForm(true)} className="w-full sm:w-auto">
                  <PlusIcon className="h-4 w-4 sm:h-5 sm:w-5 mr-2" />
                  New Activity
                </Button>
              </div>
            </div>
          ) : (
            <>
              {/* Mobile Card View */}
              <div className="block md:hidden divide-y divide-gray-200 dark:divide-gray-700 bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
                {activities.map((activity) => {
                  const TypeIcon = activityTypeIcons[activity.activity_type] ?? DocumentTextIcon;
                  const isOverdue =
                    !activity.is_completed &&
                    activity.due_date &&
                    new Date(activity.due_date) < new Date();
                  return (
                    <div
                      key={activity.id}
                      className={clsx(
                        'p-4 hover:bg-gray-50 dark:hover:bg-gray-700/50',
                        activity.is_completed && 'opacity-60'
                      )}
                    >
                      <div className="flex items-start gap-3">
                        <div className="p-1.5 rounded-lg bg-gray-100 dark:bg-gray-700 flex-shrink-0">
                          <TypeIcon className="h-4 w-4 text-gray-500 dark:text-gray-400" aria-hidden="true" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-2">
                            <h4
                              className={clsx(
                                'text-sm font-medium text-gray-900 dark:text-gray-100 truncate',
                                activity.is_completed && 'line-through text-gray-500 dark:text-gray-400'
                              )}
                            >
                              {activity.subject}
                            </h4>
                            <span className={clsx(
                              'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium flex-shrink-0',
                              priorityBadgeClasses[activity.priority] ?? priorityBadgeClasses.normal
                            )}>
                              {activity.priority}
                            </span>
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                            <span className="capitalize">{activity.activity_type}</span>
                            {activity.entity_type && (
                              <span className="truncate">
                                {activity.entity_type} #{activity.entity_id}
                              </span>
                            )}
                            {activity.due_date ? (
                              <span className={clsx('flex items-center gap-1', isOverdue ? 'text-red-600 dark:text-red-400' : '')}>
                                <CalendarIcon className="h-3 w-3 flex-shrink-0" aria-hidden="true" />
                                {new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(new Date(activity.due_date))}
                              </span>
                            ) : activity.scheduled_at ? (
                              <span className="flex items-center gap-1">
                                <ClockIcon className="h-3 w-3 flex-shrink-0" aria-hidden="true" />
                                {new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(new Date(activity.scheduled_at))}
                              </span>
                            ) : null}
                          </div>
                          <div className="mt-2 flex items-center gap-1">
                            {!activity.is_completed && (
                              <button
                                onClick={() => handleComplete(activity.id)}
                                className="px-2 py-1 text-xs font-medium text-green-700 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/20 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-500"
                                aria-label={`Complete ${activity.subject}`}
                              >
                                Complete
                              </button>
                            )}
                            <button
                              onClick={() => handleEdit(activity)}
                              className="px-2 py-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                              aria-label={`Edit ${activity.subject}`}
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => handleDeleteClick(activity)}
                              className="px-2 py-1 text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                              aria-label={`Delete ${activity.subject}`}
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Desktop Card View */}
              <div className="hidden md:block space-y-4">
                {activities.map((activity) => (
                  <ActivityCard
                    key={activity.id}
                    activity={activity}
                    onComplete={handleComplete}
                    onEdit={() => handleEdit(activity)}
                    onDelete={(id) => {
                      const found = activities.find((a) => a.id === id);
                      if (found) handleDeleteClick(found);
                    }}
                  />
                ))}
              </div>
            </>
          )}

          {/* Pagination */}
          {activitiesData && activitiesData.pages > 1 && (
            <div className="flex flex-col sm:flex-row items-center justify-center gap-2 sm:gap-3 pt-4">
              <div className="flex items-center gap-2 w-full sm:w-auto">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={filters.page === 1}
                  onClick={() => updateFilter('page', String((filters.page || 1) - 1))}
                  className="flex-1 sm:flex-none"
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={filters.page === activitiesData.pages}
                  onClick={() => updateFilter('page', String((filters.page || 1) + 1))}
                  className="flex-1 sm:flex-none"
                >
                  Next
                </Button>
              </div>
              <div className="flex items-center gap-2 order-first sm:order-none">
                <span className="text-xs sm:text-sm text-gray-600 dark:text-gray-400">
                  Page {filters.page} of {activitiesData.pages}
                </span>
                <select
                  value={filters.page_size}
                  onChange={(e) => updateFilter('page_size', e.target.value)}
                  aria-label="Results per page"
                  className="text-xs sm:text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 px-2 py-1"
                >
                  <option value={10}>10 / page</option>
                  <option value={20}>20 / page</option>
                  <option value={50}>50 / page</option>
                  <option value={100}>100 / page</option>
                </select>
              </div>
            </div>
          )}
        </div>
      ) : viewMode === 'timeline' ? (
        <ActivityTimeline
          items={timelineItems}
          onComplete={handleComplete}
          emptyMessage="Create your first activity to see it here"
        />
      ) : (
        <CalendarView />
      )}

      {/* Form Modal - fullscreen on mobile */}
      <Modal
        isOpen={showForm}
        onClose={handleFormCancel}
        title={editingActivity ? 'Edit Activity' : 'New Activity'}
        size="lg"
        fullScreenOnMobile
      >
        <ActivityForm
          activity={editingActivity || undefined}
          onSubmit={handleFormSubmit}
          onCancel={handleFormCancel}
          isLoading={createActivity.isPending || updateActivity.isPending}
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete Activity"
        message={`Are you sure you want to delete "${deleteConfirm.activity?.subject}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteActivity.isPending}
      />
    </div>
  );
}

export default ActivitiesPage;

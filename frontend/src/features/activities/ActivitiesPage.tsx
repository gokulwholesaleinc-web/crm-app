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
import {
  useActivities,
  useUserTimeline,
  useCreateActivity,
  useUpdateActivity,
  useDeleteActivity,
  useCompleteActivity,
} from '../../hooks/useActivities';
import type { Activity, ActivityCreate, ActivityUpdate, ActivityFilters } from '../../types';

type ViewMode = 'list' | 'timeline';

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

export function ActivitiesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [showFilters, setShowFilters] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingActivity, setEditingActivity] = useState<Activity | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; activity: Activity | null }>({
    isOpen: false,
    activity: null,
  });

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

  // Fetch activities
  const { data: activitiesData, isLoading: isLoadingList } = useActivities(filters);
  const { data: timelineData, isLoading: isLoadingTimeline } = useUserTimeline(
    filters.activity_type
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
      console.error('Failed to complete activity:', error);
    }
  };

  const handleDeleteClick = (activity: Activity) => {
    setDeleteConfirm({ isOpen: true, activity });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm.activity) return;
    try {
      await deleteActivity.mutateAsync(deleteConfirm.activity.id);
      setDeleteConfirm({ isOpen: false, activity: null });
    } catch (error) {
      console.error('Failed to delete activity:', error);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm({ isOpen: false, activity: null });
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
      console.error('Failed to save activity:', error);
    }
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditingActivity(null);
  };

  const isLoading = viewMode === 'list' ? isLoadingList : isLoadingTimeline;
  const activities = activitiesData?.items || [];
  const timelineItems = timelineData?.items || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Activities</h1>
          <p className="text-sm text-gray-500 mt-1">
            Track and manage all your activities in one place
          </p>
        </div>
        <Button leftIcon={<PlusIcon className="h-5 w-5" />} onClick={() => setShowForm(true)}>
          New Activity
        </Button>
      </div>

      {/* Activity Type Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex -mb-px space-x-6" aria-label="Activity types">
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
                  'flex items-center gap-2 py-3 px-1 border-b-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'border-primary-500 text-primary-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                )}
              >
                {Icon && <Icon className="h-4 w-4" />}
                {type.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setViewMode('list')}
            className={clsx(
              'p-2 rounded-lg transition-colors',
              viewMode === 'list'
                ? 'bg-primary-100 text-primary-600'
                : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'
            )}
            title="List view"
          >
            <ListBulletIcon className="h-5 w-5" />
          </button>
          <button
            onClick={() => setViewMode('timeline')}
            className={clsx(
              'p-2 rounded-lg transition-colors',
              viewMode === 'timeline'
                ? 'bg-primary-100 text-primary-600'
                : 'text-gray-400 hover:bg-gray-100 hover:text-gray-600'
            )}
            title="Timeline view"
          >
            <ClockIcon className="h-5 w-5" />
          </button>
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<FunnelIcon className="h-4 w-4" />}
            onClick={() => setShowFilters(!showFilters)}
          >
            Filters
          </Button>
        </div>

        {viewMode === 'list' && activitiesData && (
          <div className="text-sm text-gray-500">
            Showing {activities.length} of {activitiesData.total} activities
          </div>
        )}
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="bg-gray-50 rounded-lg p-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
        <div className="flex items-center justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : viewMode === 'list' ? (
        <div className="space-y-4">
          {activities.length === 0 ? (
            <div className="text-center py-12">
              <DocumentTextIcon className="mx-auto h-12 w-12 text-gray-400" />
              <h3 className="mt-2 text-sm font-medium text-gray-900">No activities</h3>
              <p className="mt-1 text-sm text-gray-500">
                Get started by creating a new activity.
              </p>
              <div className="mt-6">
                <Button onClick={() => setShowForm(true)}>
                  <PlusIcon className="h-5 w-5 mr-2" />
                  New Activity
                </Button>
              </div>
            </div>
          ) : (
            activities.map((activity) => (
              <ActivityCard
                key={activity.id}
                activity={activity}
                onComplete={handleComplete}
                onEdit={() => handleEdit(activity)}
                onDelete={(id) => {
                  const activity = activities.find((a) => a.id === id);
                  if (activity) handleDeleteClick(activity);
                }}
              />
            ))
          )}

          {/* Pagination */}
          {activitiesData && activitiesData.pages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-4">
              <Button
                variant="secondary"
                size="sm"
                disabled={filters.page === 1}
                onClick={() => updateFilter('page', String((filters.page || 1) - 1))}
              >
                Previous
              </Button>
              <span className="text-sm text-gray-600">
                Page {filters.page} of {activitiesData.pages}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={filters.page === activitiesData.pages}
                onClick={() => updateFilter('page', String((filters.page || 1) + 1))}
              >
                Next
              </Button>
            </div>
          )}
        </div>
      ) : (
        <ActivityTimeline
          items={timelineItems}
          onComplete={handleComplete}
          emptyMessage="Create your first activity to see it here"
        />
      )}

      {/* Form Modal */}
      <Modal
        isOpen={showForm}
        onClose={handleFormCancel}
        title={editingActivity ? 'Edit Activity' : 'New Activity'}
        size="lg"
      >
        <ActivityForm
          activity={editingActivity || undefined}
          entityType="user"
          entityId={0}
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

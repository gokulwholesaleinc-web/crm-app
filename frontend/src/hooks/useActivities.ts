/**
 * Activities hooks using the entity CRUD factory pattern.
 * Uses TanStack Query for data fetching and caching.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createEntityHooks, createQueryKeys } from './useEntityCRUD';
import { useAuthQuery } from './useAuthQuery';
import { activitiesApi } from '../api/activities';
import type {
  Activity,
  ActivityCreate,
  ActivityUpdate,
  ActivityFilters,
  CompleteActivityRequest,
} from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const activityKeys = {
  ...createQueryKeys('activities'),
  timeline: (entityType: string, entityId: number) =>
    ['activities', 'timeline', entityType, entityId] as const,
};

// =============================================================================
// Entity CRUD Hooks using Factory Pattern
// =============================================================================

const activityEntityHooks = createEntityHooks<
  Activity,
  ActivityCreate,
  ActivityUpdate,
  ActivityFilters
>({
  entityName: 'activities',
  baseUrl: '/api/activities',
  queryKey: 'activities',
});

/**
 * Hook to fetch a paginated list of activities
 */
export function useActivities(filters?: ActivityFilters) {
  return activityEntityHooks.useList(filters);
}

/**
 * Hook to fetch a single activity by ID
 */
export function useActivity(id: number | undefined) {
  return activityEntityHooks.useOne(id);
}

/**
 * Hook to create a new activity
 */
export function useCreateActivity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ActivityCreate) => activitiesApi.create(data),
    onSuccess: (newActivity) => {
      queryClient.invalidateQueries({ queryKey: activityKeys.lists() });
      // Also invalidate timeline for the related entity
      queryClient.invalidateQueries({
        queryKey: activityKeys.timeline(newActivity.entity_type, newActivity.entity_id),
      });
    },
  });
}

/**
 * Hook to update an activity
 */
export function useUpdateActivity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ActivityUpdate }) =>
      activitiesApi.update(id, data),
    onSuccess: (updatedActivity, { id }) => {
      queryClient.invalidateQueries({ queryKey: activityKeys.lists() });
      queryClient.invalidateQueries({ queryKey: activityKeys.detail(id) });
      queryClient.invalidateQueries({
        queryKey: activityKeys.timeline(updatedActivity.entity_type, updatedActivity.entity_id),
      });
    },
  });
}

/**
 * Hook to delete an activity
 */
export function useDeleteActivity() {
  return activityEntityHooks.useDelete();
}

// =============================================================================
// Timeline Hooks
// =============================================================================

/**
 * Hook to fetch timeline for an entity
 */
export function useTimeline(entityType: string, entityId: number, activityTypes?: string) {
  return useAuthQuery({
    queryKey: activityKeys.timeline(entityType, entityId),
    queryFn: () => activitiesApi.getEntityTimeline(entityType, entityId, 50, activityTypes),
    enabled: !!entityType && !!entityId,
  });
}

/**
 * Hook to fetch user's timeline
 */
export function useUserTimeline(activityTypes?: string) {
  return useAuthQuery({
    queryKey: ['activities', 'user-timeline', activityTypes],
    queryFn: () => activitiesApi.getUserTimeline(50, true, activityTypes),
  });
}

// =============================================================================
// Task and Activity Management Hooks
// =============================================================================

/**
 * Hook to fetch upcoming activities
 */
export function useUpcomingActivities(daysAhead = 7) {
  return useAuthQuery({
    queryKey: ['activities', 'upcoming', daysAhead],
    queryFn: () => activitiesApi.getUpcoming(daysAhead),
  });
}

/**
 * Hook to fetch overdue activities
 */
export function useOverdueActivities() {
  return useAuthQuery({
    queryKey: ['activities', 'overdue'],
    queryFn: () => activitiesApi.getOverdue(),
  });
}

/**
 * Hook to fetch user's tasks
 */
export function useMyTasks(includeCompleted = false) {
  return useAuthQuery({
    queryKey: ['activities', 'my-tasks', includeCompleted],
    queryFn: () => activitiesApi.getMyTasks(includeCompleted),
  });
}

/**
 * Hook to complete an activity
 */
export function useCompleteActivity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data?: CompleteActivityRequest }) =>
      activitiesApi.complete(id, data),
    onSuccess: (updatedActivity, { id }) => {
      queryClient.invalidateQueries({ queryKey: activityKeys.lists() });
      queryClient.invalidateQueries({ queryKey: activityKeys.detail(id) });
      queryClient.invalidateQueries({
        queryKey: activityKeys.timeline(updatedActivity.entity_type, updatedActivity.entity_id),
      });
    },
  });
}

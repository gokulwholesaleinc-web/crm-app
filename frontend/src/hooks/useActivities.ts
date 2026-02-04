/**
 * Activities hooks using TanStack Query
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { activitiesApi } from '../api/activities';
import type {
  Activity,
  ActivityCreate,
  ActivityUpdate,
  ActivityFilters,
  CompleteActivityRequest,
} from '../types';

// Query keys
export const activityKeys = {
  all: ['activities'] as const,
  lists: () => [...activityKeys.all, 'list'] as const,
  list: (filters?: ActivityFilters) => [...activityKeys.lists(), filters] as const,
  details: () => [...activityKeys.all, 'detail'] as const,
  detail: (id: number) => [...activityKeys.details(), id] as const,
  timeline: (entityType: string, entityId: number) =>
    [...activityKeys.all, 'timeline', entityType, entityId] as const,
};

/**
 * Hook to fetch a paginated list of activities
 */
export function useActivities(filters?: ActivityFilters) {
  return useQuery({
    queryKey: activityKeys.list(filters),
    queryFn: () => activitiesApi.list(filters),
  });
}

/**
 * Hook to fetch a single activity by ID
 */
export function useActivity(id: number | undefined) {
  return useQuery({
    queryKey: activityKeys.detail(id!),
    queryFn: () => activitiesApi.get(id!),
    enabled: !!id,
  });
}

/**
 * Hook to fetch timeline for an entity
 */
export function useTimeline(entityType: string, entityId: number, activityTypes?: string) {
  return useQuery({
    queryKey: activityKeys.timeline(entityType, entityId),
    queryFn: () => activitiesApi.getEntityTimeline(entityType, entityId, 50, activityTypes),
    enabled: !!entityType && !!entityId,
  });
}

/**
 * Hook to fetch user's timeline
 */
export function useUserTimeline(activityTypes?: string) {
  return useQuery({
    queryKey: [...activityKeys.all, 'user-timeline', activityTypes],
    queryFn: () => activitiesApi.getUserTimeline(50, true, activityTypes),
  });
}

/**
 * Hook to fetch upcoming activities
 */
export function useUpcomingActivities(daysAhead = 7) {
  return useQuery({
    queryKey: [...activityKeys.all, 'upcoming', daysAhead],
    queryFn: () => activitiesApi.getUpcoming(daysAhead),
  });
}

/**
 * Hook to fetch overdue activities
 */
export function useOverdueActivities() {
  return useQuery({
    queryKey: [...activityKeys.all, 'overdue'],
    queryFn: () => activitiesApi.getOverdue(),
  });
}

/**
 * Hook to fetch user's tasks
 */
export function useMyTasks(includeCompleted = false) {
  return useQuery({
    queryKey: [...activityKeys.all, 'my-tasks', includeCompleted],
    queryFn: () => activitiesApi.getMyTasks(includeCompleted),
  });
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => activitiesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: activityKeys.lists() });
    },
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

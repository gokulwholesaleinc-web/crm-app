/**
 * Activities API
 */

import { apiClient } from './client';
import type {
  Activity,
  ActivityCreate,
  ActivityUpdate,
  ActivityListResponse,
  ActivityFilters,
  TimelineResponse,
  CompleteActivityRequest,
} from '../types';

const ACTIVITIES_BASE = '/api/activities';

// =============================================================================
// Activities CRUD
// =============================================================================

/**
 * List activities with pagination and filters
 */
export const listActivities = async (
  filters: ActivityFilters = {}
): Promise<ActivityListResponse> => {
  const response = await apiClient.get<ActivityListResponse>(ACTIVITIES_BASE, {
    params: filters,
  });
  return response.data;
};

/**
 * Get an activity by ID
 */
export const getActivity = async (activityId: number): Promise<Activity> => {
  const response = await apiClient.get<Activity>(`${ACTIVITIES_BASE}/${activityId}`);
  return response.data;
};

/**
 * Create a new activity
 */
export const createActivity = async (activityData: ActivityCreate): Promise<Activity> => {
  const response = await apiClient.post<Activity>(ACTIVITIES_BASE, activityData);
  return response.data;
};

/**
 * Update an activity
 */
export const updateActivity = async (
  activityId: number,
  activityData: ActivityUpdate
): Promise<Activity> => {
  const response = await apiClient.patch<Activity>(
    `${ACTIVITIES_BASE}/${activityId}`,
    activityData
  );
  return response.data;
};

/**
 * Delete an activity
 */
export const deleteActivity = async (activityId: number): Promise<void> => {
  await apiClient.delete(`${ACTIVITIES_BASE}/${activityId}`);
};

/**
 * Mark an activity as completed
 */
export const completeActivity = async (
  activityId: number,
  request: CompleteActivityRequest = {}
): Promise<Activity> => {
  const response = await apiClient.post<Activity>(
    `${ACTIVITIES_BASE}/${activityId}/complete`,
    request
  );
  return response.data;
};

// =============================================================================
// Tasks
// =============================================================================

/**
 * Get tasks assigned to or owned by current user
 */
export const getMyTasks = async (
  includeCompleted = false,
  limit = 50
): Promise<Activity[]> => {
  const response = await apiClient.get<Activity[]>(`${ACTIVITIES_BASE}/my-tasks`, {
    params: {
      include_completed: includeCompleted,
      limit,
    },
  });
  return response.data;
};

// =============================================================================
// Timeline
// =============================================================================

/**
 * Get activity timeline for an entity
 */
export const getEntityTimeline = async (
  entityType: string,
  entityId: number,
  limit = 50,
  activityTypes?: string
): Promise<TimelineResponse> => {
  const response = await apiClient.get<TimelineResponse>(
    `${ACTIVITIES_BASE}/timeline/entity/${entityType}/${entityId}`,
    {
      params: {
        limit,
        ...(activityTypes && { activity_types: activityTypes }),
      },
    }
  );
  return response.data;
};

/**
 * Get activity timeline for current user
 */
export const getUserTimeline = async (
  limit = 50,
  includeAssigned = true,
  activityTypes?: string
): Promise<TimelineResponse> => {
  const response = await apiClient.get<TimelineResponse>(
    `${ACTIVITIES_BASE}/timeline/user`,
    {
      params: {
        limit,
        include_assigned: includeAssigned,
        ...(activityTypes && { activity_types: activityTypes }),
      },
    }
  );
  return response.data;
};

/**
 * Get upcoming scheduled activities
 */
export const getUpcomingActivities = async (
  daysAhead = 7,
  limit = 20
): Promise<TimelineResponse> => {
  const response = await apiClient.get<TimelineResponse>(`${ACTIVITIES_BASE}/upcoming`, {
    params: {
      days_ahead: daysAhead,
      limit,
    },
  });
  return response.data;
};

/**
 * Get overdue tasks
 */
export const getOverdueActivities = async (limit = 20): Promise<TimelineResponse> => {
  const response = await apiClient.get<TimelineResponse>(`${ACTIVITIES_BASE}/overdue`, {
    params: { limit },
  });
  return response.data;
};

// =============================================================================
// Calendar
// =============================================================================

export interface CalendarActivity {
  id: number;
  activity_type: string;
  subject: string;
  description: string | null;
  scheduled_at: string | null;
  due_date: string | null;
  is_completed: boolean;
  priority: string;
  entity_type: string;
  entity_id: number;
  meeting_location?: string | null;
}

export interface CalendarResponse {
  start_date: string;
  end_date: string;
  dates: Record<string, CalendarActivity[]>;
  total_activities: number;
}

/**
 * Get activities for calendar view
 */
export const getCalendarActivities = async (
  startDate: string,
  endDate: string,
  activityType?: string,
  ownerId?: number
): Promise<CalendarResponse> => {
  const response = await apiClient.get<CalendarResponse>(
    `${ACTIVITIES_BASE}/calendar`,
    {
      params: {
        start_date: startDate,
        end_date: endDate,
        ...(activityType && { activity_type: activityType }),
        ...(ownerId && { owner_id: ownerId }),
      },
    }
  );
  return response.data;
};

// Export all activity functions
export const activitiesApi = {
  // CRUD
  list: listActivities,
  get: getActivity,
  create: createActivity,
  update: updateActivity,
  delete: deleteActivity,
  complete: completeActivity,
  // Tasks
  getMyTasks,
  // Timeline
  getEntityTimeline,
  getUserTimeline,
  getUpcoming: getUpcomingActivities,
  getOverdue: getOverdueActivities,
  // Calendar
  getCalendarActivities,
};

export default activitiesApi;

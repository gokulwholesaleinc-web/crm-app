/**
 * Activity Types
 */

import type { PaginatedResponse } from './common';

export type ActivityType = 'call' | 'email' | 'meeting' | 'task' | 'note';
export type EntityType = 'contact' | 'company' | 'lead' | 'opportunity';
export type Priority = 'low' | 'normal' | 'high' | 'urgent';

export interface ActivityBase {
  activity_type: string;
  subject: string;
  description?: string | null;
  entity_type: string;
  entity_id: number;
  scheduled_at?: string | null;
  due_date?: string | null;
  priority: string;
  owner_id?: number | null;
  assigned_to_id?: number | null;
}

export interface ActivityCreate extends Omit<ActivityBase, 'entity_type' | 'entity_id'> {
  entity_type?: string;
  entity_id?: number;
  // Call-specific
  call_duration_minutes?: number | null;
  call_outcome?: string | null;
  // Email-specific
  email_to?: string | null;
  email_cc?: string | null;
  // Meeting-specific
  meeting_location?: string | null;
  meeting_attendees?: string | null;
  // Task-specific
  task_reminder_at?: string | null;
}

export interface ActivityUpdate {
  subject?: string | null;
  description?: string | null;
  scheduled_at?: string | null;
  due_date?: string | null;
  priority?: string | null;
  is_completed?: boolean | null;
  completed_at?: string | null;
  owner_id?: number | null;
  assigned_to_id?: number | null;
  // Call-specific
  call_duration_minutes?: number | null;
  call_outcome?: string | null;
  // Email-specific
  email_to?: string | null;
  email_cc?: string | null;
  email_opened?: boolean | null;
  // Meeting-specific
  meeting_location?: string | null;
  meeting_attendees?: string | null;
  // Task-specific
  task_reminder_at?: string | null;
}

export interface Activity extends ActivityBase {
  id: number;
  is_completed: boolean;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  // Call-specific
  call_duration_minutes?: number | null;
  call_outcome?: string | null;
  // Email-specific
  email_to?: string | null;
  email_cc?: string | null;
  email_opened?: boolean | null;
  // Meeting-specific
  meeting_location?: string | null;
  meeting_attendees?: string | null;
  // Task-specific
  task_reminder_at?: string | null;
}

export type ActivityListResponse = PaginatedResponse<Activity>;

export interface ActivityFilters {
  page?: number;
  page_size?: number;
  entity_type?: string;
  entity_id?: number;
  activity_type?: string;
  owner_id?: number;
  assigned_to_id?: number;
  is_completed?: boolean;
  priority?: string;
}

export interface TimelineItem {
  id: number;
  activity_type: string;
  subject: string;
  description?: string | null;
  entity_type: string;
  entity_id: number;
  scheduled_at?: string | null;
  due_date?: string | null;
  completed_at?: string | null;
  is_completed: boolean;
  priority: string;
  created_at: string;
  owner_id?: number | null;
  assigned_to_id?: number | null;
  call_duration_minutes?: number | null;
  call_outcome?: string | null;
  meeting_location?: string | null;
}

export interface TimelineResponse {
  items: TimelineItem[];
}

export interface CompleteActivityRequest {
  notes?: string | null;
}

/**
 * Email API client
 */

import { apiClient } from './client';

export interface SendEmailPayload {
  to_email: string;
  subject: string;
  body: string;
  entity_type?: string;
  entity_id?: number;
}

export interface SendTemplateEmailPayload {
  to_email: string;
  template_id: number;
  variables?: Record<string, string>;
  entity_type?: string;
  entity_id?: number;
}

export interface EmailQueueItem {
  id: number;
  to_email: string;
  subject: string;
  body: string;
  status: string;
  attempts: number;
  error: string | null;
  created_at: string;
  sent_at: string | null;
  opened_at: string | null;
  clicked_at: string | null;
  open_count: number;
  click_count: number;
  entity_type: string | null;
  entity_id: number | null;
  template_id: number | null;
  campaign_id: number | null;
  sent_by_id: number | null;
}

export interface EmailListResponse {
  items: EmailQueueItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export const emailApi = {
  send: (data: SendEmailPayload) =>
    apiClient.post<EmailQueueItem>('/api/email/send', data).then((r) => r.data),

  sendTemplate: (data: SendTemplateEmailPayload) =>
    apiClient.post<EmailQueueItem>('/api/email/send-template', data).then((r) => r.data),

  list: (params?: { page?: number; page_size?: number; entity_type?: string; entity_id?: number; status?: string }) =>
    apiClient.get<EmailListResponse>('/api/email', { params }).then((r) => r.data),

  getById: (id: number) =>
    apiClient.get<EmailQueueItem>(`/api/email/${id}`).then((r) => r.data),
};

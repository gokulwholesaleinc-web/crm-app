/**
 * React Query hooks for email operations.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { emailApi, SendEmailPayload, SendTemplateEmailPayload } from '../api/email';

export const emailKeys = {
  all: ['emails'] as const,
  list: (params?: Record<string, unknown>) => [...emailKeys.all, 'list', params] as const,
  entity: (entityType: string, entityId: number) =>
    [...emailKeys.all, 'entity', entityType, entityId] as const,
  detail: (id: number) => [...emailKeys.all, 'detail', id] as const,
  thread: (entityType: string, entityId: number, page: number) =>
    [...emailKeys.all, 'thread', entityType, entityId, page] as const,
};

export function useEmailList(params?: {
  page?: number;
  page_size?: number;
  entity_type?: string;
  entity_id?: number;
  status?: string;
}) {
  return useQuery({
    queryKey: emailKeys.list(params as Record<string, unknown>),
    queryFn: () => emailApi.list(params),
  });
}

export function useEntityEmails(entityType: string, entityId: number) {
  return useQuery({
    queryKey: emailKeys.entity(entityType, entityId),
    queryFn: () => emailApi.list({ entity_type: entityType, entity_id: entityId }),
    enabled: !!entityType && !!entityId,
  });
}

export function useSendEmail() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SendEmailPayload) => emailApi.send(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: emailKeys.all });
    },
  });
}

export function useSendTemplateEmail() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SendTemplateEmailPayload) => emailApi.sendTemplate(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: emailKeys.all });
    },
  });
}

export function useEmailThread(entityType: string, entityId: number, page = 1, pageSize = 50) {
  return useQuery({
    queryKey: emailKeys.thread(entityType, entityId, page),
    queryFn: () => emailApi.thread({ entity_type: entityType, entity_id: entityId, page, page_size: pageSize }),
    enabled: !!entityType && !!entityId,
  });
}

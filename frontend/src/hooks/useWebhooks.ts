/**
 * Webhooks hooks using TanStack Query.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { webhooksApi } from '../api/webhooks';
import { useAuthQuery } from './useAuthQuery';
import type { WebhookCreate, WebhookUpdate } from '../types';

export const webhookKeys = {
  all: ['webhooks'] as const,
  lists: () => ['webhooks', 'list'] as const,
  list: (params?: { is_active?: boolean }) => ['webhooks', 'list', params] as const,
  details: () => ['webhooks', 'detail'] as const,
  detail: (id: number) => ['webhooks', 'detail', id] as const,
  deliveries: (id: number) => ['webhooks', 'deliveries', id] as const,
};

export function useWebhooks(params?: { is_active?: boolean }) {
  return useAuthQuery({
    queryKey: webhookKeys.list(params),
    queryFn: () => webhooksApi.list(params),
  });
}

export function useWebhook(id: number | undefined) {
  return useAuthQuery({
    queryKey: webhookKeys.detail(id!),
    queryFn: () => webhooksApi.get(id!),
    enabled: !!id,
  });
}

export function useWebhookDeliveries(id: number | undefined) {
  return useAuthQuery({
    queryKey: webhookKeys.deliveries(id!),
    queryFn: () => webhooksApi.getDeliveries(id!),
    enabled: !!id,
  });
}

export function useCreateWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: WebhookCreate) => webhooksApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: webhookKeys.lists() });
    },
  });
}

export function useUpdateWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: WebhookUpdate }) =>
      webhooksApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: webhookKeys.lists() });
      queryClient.invalidateQueries({ queryKey: webhookKeys.detail(id) });
    },
  });
}

export function useDeleteWebhook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => webhooksApi.delete(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: webhookKeys.lists() });
      queryClient.removeQueries({ queryKey: webhookKeys.detail(id) });
    },
  });
}

export function useTestWebhook() {
  return useMutation({
    mutationFn: (id: number) => webhooksApi.test(id),
  });
}

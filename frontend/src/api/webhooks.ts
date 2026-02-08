/**
 * Webhooks API
 */

import { apiClient } from './client';
import type {
  Webhook,
  WebhookCreate,
  WebhookUpdate,
  WebhookDelivery,
} from '../types';

const BASE = '/api/webhooks';

export const listWebhooks = async (
  params?: { is_active?: boolean }
): Promise<Webhook[]> => {
  const response = await apiClient.get<Webhook[]>(BASE, { params });
  return response.data;
};

export const getWebhook = async (id: number): Promise<Webhook> => {
  const response = await apiClient.get<Webhook>(`${BASE}/${id}`);
  return response.data;
};

export const createWebhook = async (data: WebhookCreate): Promise<Webhook> => {
  const response = await apiClient.post<Webhook>(BASE, data);
  return response.data;
};

export const updateWebhook = async (
  id: number,
  data: WebhookUpdate
): Promise<Webhook> => {
  const response = await apiClient.put<Webhook>(`${BASE}/${id}`, data);
  return response.data;
};

export const deleteWebhook = async (id: number): Promise<void> => {
  await apiClient.delete(`${BASE}/${id}`);
};

export const getWebhookDeliveries = async (
  id: number
): Promise<WebhookDelivery[]> => {
  const response = await apiClient.get<WebhookDelivery[]>(
    `${BASE}/${id}/deliveries`
  );
  return response.data;
};

export const testWebhook = async (id: number): Promise<{ status: string; message: string }> => {
  const response = await apiClient.post(`${BASE}/${id}/test`);
  return response.data;
};

export const webhooksApi = {
  list: listWebhooks,
  get: getWebhook,
  create: createWebhook,
  update: updateWebhook,
  delete: deleteWebhook,
  getDeliveries: getWebhookDeliveries,
  test: testWebhook,
};

export default webhooksApi;

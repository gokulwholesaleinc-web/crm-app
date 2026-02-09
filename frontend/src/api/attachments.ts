/**
 * Attachments API
 */

import { apiClient } from './client';

export interface AttachmentResponse {
  id: number;
  filename: string;
  original_filename: string;
  file_size: number;
  mime_type: string;
  entity_type: string;
  entity_id: number;
  uploaded_by: number | null;
  created_at: string;
}

export interface AttachmentListResponse {
  items: AttachmentResponse[];
  total: number;
}

const BASE = '/api/attachments';

export const uploadAttachment = async (
  file: File,
  entityType: string,
  entityId: number,
): Promise<AttachmentResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('entity_type', entityType);
  formData.append('entity_id', String(entityId));

  const response = await apiClient.post<AttachmentResponse>(`${BASE}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

export const listAttachments = async (
  entityType: string,
  entityId: number,
): Promise<AttachmentListResponse> => {
  const response = await apiClient.get<AttachmentListResponse>(
    `${BASE}/${entityType}/${entityId}`,
  );
  return response.data;
};

export const deleteAttachment = async (attachmentId: number): Promise<void> => {
  await apiClient.delete(`${BASE}/${attachmentId}`);
};

export const getDownloadUrl = (attachmentId: number): string => {
  const baseUrl = apiClient.defaults.baseURL || '';
  return `${baseUrl}${BASE}/${attachmentId}/download`;
};

export const attachmentsApi = {
  upload: uploadAttachment,
  list: listAttachments,
  delete: deleteAttachment,
  getDownloadUrl,
};

export default attachmentsApi;

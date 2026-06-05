/**
 * Attachments API
 */

import { apiClient, getToken } from './client';

export interface AttachmentResponse {
  id: number;
  filename: string;
  original_filename: string;
  file_size: number;
  mime_type: string;
  entity_type: string;
  entity_id: number;
  category: string | null;
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
  category?: string,
): Promise<AttachmentResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('entity_type', entityType);
  formData.append('entity_id', String(entityId));
  if (category) {
    formData.append('category', category);
  }

  const response = await apiClient.post<AttachmentResponse>(`${BASE}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

export const listAttachments = async (
  entityType: string,
  entityId: number,
  category?: string,
): Promise<AttachmentListResponse> => {
  const params = category ? { category } : {};
  const response = await apiClient.get<AttachmentListResponse>(
    `${BASE}/${entityType}/${entityId}`,
    { params },
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

/**
 * Download an attachment by id. Asks the backend for a presigned URL as JSON
 * (``?as_json=1``) — rather than following the default 307 to R2, which returns
 * no CORS headers — then anchor-clicks the presigned URL (a top-level
 * navigation that bypasses CORS). Throws on a non-OK response so callers can
 * surface a failure toast.
 */
export const downloadAttachmentFile = async (
  attachmentId: number,
  filename: string,
): Promise<void> => {
  const token = getToken();
  const response = await fetch(`${getDownloadUrl(attachmentId)}?as_json=1`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) throw new Error('Download failed');
  const { download_url: downloadUrl } = (await response.json()) as {
    download_url: string;
  };
  // Guard a malformed/empty 200 body so it surfaces as a failure (caller toast)
  // rather than silently anchor-clicking a dead 'undefined' URL.
  if (!downloadUrl) throw new Error('Download failed');
  const link = document.createElement('a');
  link.href = downloadUrl;
  link.download = filename;
  link.rel = 'noopener noreferrer';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

/**
 * Open an attachment for in-browser viewing in a new tab. Asks the backend for
 * an INLINE-disposition presigned URL (``?as_json=1&inline=1``) — the backend
 * only honours ``inline`` for vetted-safe types (PDF / image), forcing a
 * download otherwise — then anchor-opens it in a new tab (a top-level
 * navigation that needs no CORS, mirroring downloadAttachmentFile). Throws on a
 * non-OK response so callers can surface a failure toast.
 */
export const viewAttachmentFile = async (attachmentId: number): Promise<void> => {
  const token = getToken();
  const response = await fetch(`${getDownloadUrl(attachmentId)}?as_json=1&inline=1`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) throw new Error('View failed');
  const { download_url: viewUrl } = (await response.json()) as {
    download_url: string;
  };
  if (!viewUrl) throw new Error('View failed');
  const link = document.createElement('a');
  link.href = viewUrl;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

export const attachmentsApi = {
  upload: uploadAttachment,
  list: listAttachments,
  delete: deleteAttachment,
  getDownloadUrl,
};


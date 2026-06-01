/**
 * Client Onboarding API (Phase 1)
 *
 * Thin wrappers over the team-library template CRUD + PDF upload/serve
 * endpoints (see build-order note §C). Mirrors the convention in
 * ``api/activities.ts`` / ``api/proposals.ts`` — ``apiClient`` calls that
 * return ``response.data``, with ``responseType: 'blob'`` for the PDF.
 */

import { apiClient } from './client';
import type {
  OnboardingTemplate,
  OnboardingTemplateCreate,
  OnboardingTemplateUpdate,
  OnboardingTemplateFilters,
  OnboardingPacket,
  OnboardingPacketDetail,
  OnboardingPacketCreate,
} from '../types';

const ONBOARDING_BASE = '/api/onboarding/templates';

/** Matches the backend cap (``_MAX_SIGNING_PDF_BYTES``, 25 MB). */
export const ONBOARDING_PDF_MAX_BYTES = 25 * 1024 * 1024;

/**
 * List templates. Global team library — no owner filter. ``service_tag``
 * narrows to one service; ``include_inactive`` surfaces retired rows.
 */
export const listOnboardingTemplates = async (
  filters: OnboardingTemplateFilters = {},
): Promise<OnboardingTemplate[]> => {
  const response = await apiClient.get<OnboardingTemplate[]>(ONBOARDING_BASE, {
    params: filters,
  });
  return response.data;
};

export const getOnboardingTemplate = async (
  templateId: number,
): Promise<OnboardingTemplate> => {
  const response = await apiClient.get<OnboardingTemplate>(
    `${ONBOARDING_BASE}/${templateId}`,
  );
  return response.data;
};

export const createOnboardingTemplate = async (
  data: OnboardingTemplateCreate,
): Promise<OnboardingTemplate> => {
  const response = await apiClient.post<OnboardingTemplate>(ONBOARDING_BASE, data);
  return response.data;
};

/**
 * Update metadata and/or field definitions. Passing ``field_definitions``
 * before a PDF has been uploaded returns 422 (bounds-validation needs the
 * page count). Pass ``pdf_version`` alongside ``field_definitions`` as an
 * optimistic-lock token — a mismatch (the PDF was replaced under the open
 * editor) returns 409.
 */
export const updateOnboardingTemplate = async (
  templateId: number,
  data: OnboardingTemplateUpdate,
): Promise<OnboardingTemplate> => {
  const response = await apiClient.patch<OnboardingTemplate>(
    `${ONBOARDING_BASE}/${templateId}`,
    data,
  );
  return response.data;
};

/**
 * Upload (or replace) the template PDF. Re-uploading bumps ``pdf_version``
 * and clears ``field_definitions`` server-side (old coords are meaningless
 * against a new PDF).
 */
export const uploadOnboardingTemplatePdf = async (
  templateId: number,
  file: File,
): Promise<OnboardingTemplate> => {
  const form = new FormData();
  form.append('file', file);
  const response = await apiClient.post<OnboardingTemplate>(
    `${ONBOARDING_BASE}/${templateId}/pdf`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return response.data;
};

/** Fetch the template PDF bytes (for the editor canvas / preview). */
export const downloadOnboardingTemplatePdf = async (
  templateId: number,
): Promise<Blob> => {
  const response = await apiClient.get(`${ONBOARDING_BASE}/${templateId}/pdf`, {
    responseType: 'blob',
  });
  return response.data;
};

/** Soft-retire a template (``is_active = false``). */
export const retireOnboardingTemplate = async (
  templateId: number,
): Promise<OnboardingTemplate> => {
  const response = await apiClient.post<OnboardingTemplate>(
    `${ONBOARDING_BASE}/${templateId}/retire`,
  );
  return response.data;
};

/** Restore a retired template (``is_active = true``). */
export const restoreOnboardingTemplate = async (
  templateId: number,
): Promise<OnboardingTemplate> => {
  const response = await apiClient.post<OnboardingTemplate>(
    `${ONBOARDING_BASE}/${templateId}/restore`,
  );
  return response.data;
};

// ---------------------------------------------------------------------------
// Phase 2 — packets (staff "select-and-send" + per-contact packet list)
// ---------------------------------------------------------------------------

const PACKETS_BASE = '/api/onboarding/packets';

/**
 * Create a packet for a contact from one or more active templates. The 201
 * response carries the one-time ``access_url`` (raw token) for staff to copy
 * and share manually — it is shown exactly once and never re-served by GET
 * (build-order note §8).
 */
export const createOnboardingPacket = async (
  data: OnboardingPacketCreate,
): Promise<OnboardingPacket> => {
  const response = await apiClient.post<OnboardingPacket>(PACKETS_BASE, data);
  return response.data;
};

/** List packets for a contact (access-checked; includes live delivery status). */
export const listOnboardingPackets = async (
  contactId: number,
): Promise<OnboardingPacket[]> => {
  const response = await apiClient.get<OnboardingPacket[]>(PACKETS_BASE, {
    params: { contact_id: contactId },
  });
  return response.data;
};

/** Single packet detail (per-doc status). */
export const getOnboardingPacket = async (
  packetId: number,
): Promise<OnboardingPacketDetail> => {
  const response = await apiClient.get<OnboardingPacketDetail>(
    `${PACKETS_BASE}/${packetId}`,
  );
  return response.data;
};

/** Revoke a live packet — kills the link and scrubs PII. */
export const revokeOnboardingPacket = async (
  packetId: number,
): Promise<OnboardingPacket> => {
  const response = await apiClient.post<OnboardingPacket>(
    `${PACKETS_BASE}/${packetId}/revoke`,
  );
  return response.data;
};

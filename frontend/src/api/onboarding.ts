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
 * page count).
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

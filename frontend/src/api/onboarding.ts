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
  OnboardingProposalSelection,
  OnboardingStarter,
  OnboardingTemplateCloneRequest,
  OnboardingTemplateFromStarterRequest,
  OnboardingBundleSummary,
  OnboardingBundleDetail,
  OnboardingBundleCreate,
  OnboardingBundleUpdate,
} from '../types';

const ONBOARDING_BASE = '/api/onboarding/templates';
const BUNDLES_BASE = '/api/onboarding/template-bundles';

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

/**
 * Re-run completion (Phase B/C) for a packet stuck in ``completion_failed`` or
 * a stale ``completing`` — the client already submitted/signed, so this
 * salvages their data instead of discarding it via revoke.
 */
export const retryOnboardingPacket = async (
  packetId: number,
): Promise<OnboardingPacket> => {
  const response = await apiClient.post<OnboardingPacket>(
    `${PACKETS_BASE}/${packetId}/retry-completion`,
  );
  return response.data;
};

export interface OnboardingResendResult {
  /** The recipient + owner e-mail addresses the notice was re-queued to. */
  resent: string[];
}

/**
 * Resend the completion notice for a completed packet. The backend mints a
 * fresh download token and e-mails a working link (the original raw token is
 * unrecoverable), so the recipient can reach their signed PDFs again.
 */
export const resendOnboardingCompletionNotice = async (
  packetId: number,
): Promise<OnboardingResendResult> => {
  const response = await apiClient.post<OnboardingResendResult>(
    `${PACKETS_BASE}/${packetId}/resend-completion-notice`,
  );
  return response.data;
};

/**
 * Re-mint a fresh access token + re-queue the *invite* for a still-live (or
 * expired) packet — distinct from {@link resendOnboardingCompletionNotice},
 * which re-sends the post-completion download notice. The original raw link
 * is unrecoverable, so this is how staff hand a client a working link again.
 * 409 for terminal states (completed/revoked/completing/abandoned). Returns
 * the refreshed packet (no raw token is ever echoed back to staff).
 */
export const resendOnboardingPacketInvite = async (
  packetId: number,
): Promise<OnboardingPacket> => {
  const response = await apiClient.post<OnboardingPacket>(
    `${PACKETS_BASE}/${packetId}/resend`,
  );
  return response.data;
};

/**
 * Rotate the access token and return the NEW one-time ``access_url`` to copy —
 * the recovery path when the original link was lost (the raw token is never
 * stored, so it can't be re-served). The previously shared link stops working.
 * Pass ``sendEmail`` to also re-queue the invite (only then is the owner's
 * Gmail required). 409 for terminal states (completed/revoked/completing/
 * abandoned).
 */
export const regenerateOnboardingPacketLink = async (
  packetId: number,
  sendEmail = false,
): Promise<OnboardingPacket> => {
  const response = await apiClient.post<OnboardingPacket>(
    `${PACKETS_BASE}/${packetId}/regenerate-link`,
    { send_email: sendEmail },
  );
  return response.data;
};

// ---------------------------------------------------------------------------
// Phase 3 — proposal → onboarding-template selections (staff curation)
// ---------------------------------------------------------------------------

const proposalSelectionsBase = (proposalId: number): string =>
  `/api/onboarding/proposals/${proposalId}/selections`;

/** List a proposal's onboarding-template selections, ordered by display_order. */
export const listProposalOnboardingSelections = async (
  proposalId: number,
): Promise<OnboardingProposalSelection[]> => {
  const response = await apiClient.get<OnboardingProposalSelection[]>(
    proposalSelectionsBase(proposalId),
  );
  return response.data;
};

/**
 * Replace the whole ordered selection list for a proposal. ``templateIds`` is
 * the full desired set in display order; a retired or PDF-less template is a
 * 422 (surface the detail to the user).
 */
export const setProposalOnboardingSelections = async (
  proposalId: number,
  templateIds: number[],
): Promise<OnboardingProposalSelection[]> => {
  const response = await apiClient.put<OnboardingProposalSelection[]>(
    proposalSelectionsBase(proposalId),
    { template_ids: templateIds },
  );
  return response.data;
};

/**
 * Reorder a proposal's selections by a permutation of their *selection* ids
 * (not template ids). Returns the re-ordered list.
 */
export const reorderProposalOnboardingSelections = async (
  proposalId: number,
  orderedIds: number[],
): Promise<OnboardingProposalSelection[]> => {
  const response = await apiClient.post<OnboardingProposalSelection[]>(
    `${proposalSelectionsBase(proposalId)}/reorder`,
    { ordered_ids: orderedIds },
  );
  return response.data;
};

/** Remove one onboarding-template selection from a proposal (204). */
export const removeProposalOnboardingSelection = async (
  proposalId: number,
  selectionId: number,
): Promise<void> => {
  await apiClient.delete(
    `${proposalSelectionsBase(proposalId)}/${selectionId}`,
  );
};

// ---------------------------------------------------------------------------
// "Saved packet" bundles + starters + clone/from-starter (wizard feature)
// ---------------------------------------------------------------------------

/** List the built-in starter templates (the wizard's example picker). */
export const listOnboardingStarters = async (): Promise<OnboardingStarter[]> => {
  const response = await apiClient.get<OnboardingStarter[]>(
    `${ONBOARDING_BASE}/starters`,
  );
  return response.data;
};

/**
 * Clone an active questionnaire/upload template into a fresh one. Omit ``name``
 * to let the backend auto-suffix ``"{source} (copy[, N])"``; an e-sign or
 * retired source, or an explicit-name collision, is a 422.
 */
export const cloneOnboardingTemplate = async (
  templateId: number,
  data: OnboardingTemplateCloneRequest = {},
): Promise<OnboardingTemplate> => {
  const response = await apiClient.post<OnboardingTemplate>(
    `${ONBOARDING_BASE}/${templateId}/clone`,
    data,
  );
  return response.data;
};

/** Instantiate a built-in starter into a fresh template. */
export const createOnboardingTemplateFromStarter = async (
  data: OnboardingTemplateFromStarterRequest,
): Promise<OnboardingTemplate> => {
  const response = await apiClient.post<OnboardingTemplate>(
    `${ONBOARDING_BASE}/from-starter`,
    data,
  );
  return response.data;
};

/** List saved packets (team library). ``includeInactive`` surfaces retired ones. */
export const listOnboardingBundles = async (
  includeInactive = false,
): Promise<OnboardingBundleSummary[]> => {
  const response = await apiClient.get<OnboardingBundleSummary[]>(BUNDLES_BASE, {
    params: { include_inactive: includeInactive },
  });
  return response.data;
};

/** One saved packet with its ordered members + per-member send-readiness. */
export const getOnboardingBundle = async (
  bundleId: number,
): Promise<OnboardingBundleDetail> => {
  const response = await apiClient.get<OnboardingBundleDetail>(
    `${BUNDLES_BASE}/${bundleId}`,
  );
  return response.data;
};

/** Create a saved packet from the wizard (mints a template per item). */
export const createOnboardingBundle = async (
  data: OnboardingBundleCreate,
): Promise<OnboardingBundleDetail> => {
  const response = await apiClient.post<OnboardingBundleDetail>(BUNDLES_BASE, data);
  return response.data;
};

/** Rename / re-describe / retire-restore a saved packet. */
export const updateOnboardingBundle = async (
  bundleId: number,
  data: OnboardingBundleUpdate,
): Promise<OnboardingBundleDetail> => {
  const response = await apiClient.patch<OnboardingBundleDetail>(
    `${BUNDLES_BASE}/${bundleId}`,
    data,
  );
  return response.data;
};

/** Reorder a saved packet's members by a permutation of their item ids. */
export const reorderOnboardingBundle = async (
  bundleId: number,
  orderedItemIds: number[],
): Promise<OnboardingBundleDetail> => {
  const response = await apiClient.post<OnboardingBundleDetail>(
    `${BUNDLES_BASE}/${bundleId}/reorder`,
    { ordered_item_ids: orderedItemIds },
  );
  return response.data;
};

/** Append an existing template to a saved packet. */
export const addOnboardingBundleItem = async (
  bundleId: number,
  templateId: number,
): Promise<OnboardingBundleDetail> => {
  const response = await apiClient.post<OnboardingBundleDetail>(
    `${BUNDLES_BASE}/${bundleId}/items`,
    { template_id: templateId },
  );
  return response.data;
};

/** Remove one member from a saved packet (refuses the last one → 422). */
export const removeOnboardingBundleItem = async (
  bundleId: number,
  itemId: number,
): Promise<void> => {
  await apiClient.delete(`${BUNDLES_BASE}/${bundleId}/items/${itemId}`);
};

/** Hard-delete a saved packet (its items cascade; minted templates remain). */
export const deleteOnboardingBundle = async (bundleId: number): Promise<void> => {
  await apiClient.delete(`${BUNDLES_BASE}/${bundleId}`);
};

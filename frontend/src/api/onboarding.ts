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

/**
 * Fetch a staff-side onboarding deliverable (a client upload or a completed
 * document PDF) as a blob and open it inline in a new tab. The blank tab is
 * claimed synchronously inside the click gesture so pop-up blockers don't
 * swallow it, then navigated once the (auth'd) bytes arrive. Throws on failure
 * so the caller can surface a toast.
 */
const openOnboardingFileInTab = async (url: string): Promise<void> => {
  const win = window.open('', '_blank');
  try {
    const response = await apiClient.get<Blob>(url, { responseType: 'blob' });
    const objectUrl = URL.createObjectURL(response.data);
    if (win && !win.closed) win.location.href = objectUrl;
    else window.open(objectUrl, '_blank', 'noopener');
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  } catch (err) {
    if (win && !win.closed) win.close();
    throw err;
  }
};

/** Open a client-uploaded file inline (staff preview). */
export const viewOnboardingPacketUpload = (
  packetId: number,
  uploadId: number,
): Promise<void> =>
  openOnboardingFileInTab(`${PACKETS_BASE}/${packetId}/uploads/${uploadId}/view`);

/** Open a completed document's generated PDF inline (staff preview). */
export const viewOnboardingPacketDocument = (
  packetId: number,
  docId: number,
): Promise<void> =>
  openOnboardingFileInTab(`${PACKETS_BASE}/${packetId}/documents/${docId}/view`);

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

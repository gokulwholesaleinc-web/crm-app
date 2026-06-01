/**
 * Proposals API
 */

import { apiClient } from './client';
import type {
  Proposal,
  ProposalCreate,
  ProposalUpdate,
  ProposalListResponse,
  ProposalFilters,
  ProposalTemplate,
  ProposalTemplateCreate,
  ProposalTemplateUpdate,
  CreateFromTemplateRequest,
  ProposalAttachment,
  ProposalSigningDocument,
  ProposalBundle,
  ProposalBundleCreate,
  ProposalBundleUpdate,
  SignatureFieldCoordsValue,
} from '../types';

const PROPOSALS_BASE = '/api/proposals';

/**
 * List proposals with pagination and filters
 */
export const listProposals = async (filters: ProposalFilters = {}): Promise<ProposalListResponse> => {
  const response = await apiClient.get<ProposalListResponse>(PROPOSALS_BASE, {
    params: filters,
  });
  return response.data;
};

/**
 * Get a proposal by ID
 */
export const getProposal = async (proposalId: number): Promise<Proposal> => {
  const response = await apiClient.get<Proposal>(`${PROPOSALS_BASE}/${proposalId}`);
  return response.data;
};

/**
 * Create a new proposal
 */
export const createProposal = async (data: ProposalCreate): Promise<Proposal> => {
  const response = await apiClient.post<Proposal>(PROPOSALS_BASE, data);
  return response.data;
};

/**
 * Update a proposal
 */
export const updateProposal = async (
  proposalId: number,
  data: ProposalUpdate
): Promise<Proposal> => {
  const response = await apiClient.patch<Proposal>(`${PROPOSALS_BASE}/${proposalId}`, data);
  return response.data;
};

/**
 * Delete a proposal
 */
export const deleteProposal = async (proposalId: number): Promise<void> => {
  await apiClient.delete(`${PROPOSALS_BASE}/${proposalId}`);
};

/**
 * Send a proposal
 */
export const sendProposal = async (proposalId: number): Promise<Proposal> => {
  const response = await apiClient.post<Proposal>(`${PROPOSALS_BASE}/${proposalId}/send`);
  return response.data;
};

/**
 * Accept a proposal (internal/admin offline-acceptance path).
 *
 * When the proposal has a placed signature box but no signature on file the
 * backend refuses with 409 unless ``acknowledgeUnsigned`` is passed — the
 * caller confirms an explicit offline acceptance without a signed document.
 */
export const acceptProposal = async (
  proposalId: number,
  acknowledgeUnsigned = false,
): Promise<Proposal> => {
  const response = await apiClient.post<Proposal>(
    `${PROPOSALS_BASE}/${proposalId}/accept`,
    undefined,
    acknowledgeUnsigned
      ? { params: { acknowledge_unsigned: true } }
      : undefined,
  );
  return response.data;
};

export const createProposalBundle = async (
  data: ProposalBundleCreate,
): Promise<ProposalBundle> => {
  const response = await apiClient.post<ProposalBundle>(`${PROPOSALS_BASE}/bundles`, data);
  return response.data;
};

export const getProposalBundle = async (bundleId: number): Promise<ProposalBundle> => {
  const response = await apiClient.get<ProposalBundle>(`${PROPOSALS_BASE}/bundles/${bundleId}`);
  return response.data;
};

export const updateProposalBundle = async (
  bundleId: number,
  data: ProposalBundleUpdate,
): Promise<ProposalBundle> => {
  const response = await apiClient.patch<ProposalBundle>(
    `${PROPOSALS_BASE}/bundles/${bundleId}`,
    data,
  );
  return response.data;
};

export const sendProposalBundle = async (bundleId: number): Promise<ProposalBundle> => {
  const response = await apiClient.post<ProposalBundle>(
    `${PROPOSALS_BASE}/bundles/${bundleId}/send`,
  );
  return response.data;
};

/**
 * Remove one option from a draft proposal bundle.
 *
 * Returns the updated bundle when 2+ options remain. Returns `null` when
 * the removal dissolved the bundle (≤1 survivor); the caller must then
 * navigate the user away from any sub-proposal view because the bundle
 * no longer exists.
 */
export const removeProposalBundleOption = async (
  bundleId: number,
  proposalId: number,
): Promise<ProposalBundle | null> => {
  const response = await apiClient.delete<ProposalBundle | ''>(
    `${PROPOSALS_BASE}/bundles/${bundleId}/options/${proposalId}`,
  );
  // 204 No Content arrives as an empty string body — surface as `null`.
  if (response.status === 204 || response.data === '' || response.data == null) {
    return null;
  }
  return response.data as ProposalBundle;
};

/**
 * Reject a proposal
 */
export const rejectProposal = async (proposalId: number): Promise<Proposal> => {
  const response = await apiClient.post<Proposal>(`${PROPOSALS_BASE}/${proposalId}/reject`);
  return response.data;
};

export const restampProposalSignedPdf = async (proposalId: number): Promise<Proposal> => {
  const response = await apiClient.post<Proposal>(
    `${PROPOSALS_BASE}/${proposalId}/restamp`,
  );
  return response.data;
};

/**
 * List proposal templates
 */
export const listProposalTemplates = async (category?: string): Promise<ProposalTemplate[]> => {
  const response = await apiClient.get<ProposalTemplate[]>(`${PROPOSALS_BASE}/templates`, {
    params: category ? { category } : undefined,
  });
  return response.data;
};

/**
 * Create a proposal template
 */
export const createProposalTemplate = async (data: ProposalTemplateCreate): Promise<ProposalTemplate> => {
  const response = await apiClient.post<ProposalTemplate>(`${PROPOSALS_BASE}/templates`, data);
  return response.data;
};

/**
 * Get a proposal template by ID
 */
export const getProposalTemplate = async (id: number): Promise<ProposalTemplate> => {
  const response = await apiClient.get<ProposalTemplate>(`${PROPOSALS_BASE}/templates/${id}`);
  return response.data;
};

/**
 * Update a proposal template
 */
export const updateProposalTemplate = async (
  id: number,
  data: ProposalTemplateUpdate
): Promise<ProposalTemplate> => {
  const response = await apiClient.patch<ProposalTemplate>(`${PROPOSALS_BASE}/templates/${id}`, data);
  return response.data;
};

/**
 * Delete a proposal template
 */
export const deleteProposalTemplate = async (id: number): Promise<void> => {
  await apiClient.delete(`${PROPOSALS_BASE}/templates/${id}`);
};

/**
 * Create a proposal from a template with merge variable replacement
 */
export const createFromTemplate = async (data: CreateFromTemplateRequest): Promise<Proposal> => {
  const response = await apiClient.post<Proposal>(`${PROPOSALS_BASE}/from-template`, data);
  return response.data;
};

/**
 * Send a proposal with branded email
 */
export const sendProposalWithEmail = async (
  proposalId: number,
  attachPdf: boolean = false
): Promise<Proposal> => {
  const response = await apiClient.post<Proposal>(
    `${PROPOSALS_BASE}/${proposalId}/send`,
    { attach_pdf: attachPdf }
  );
  return response.data;
};

/**
 * Download a branded proposal PDF
 */
export const downloadProposalPDF = async (proposalId: number): Promise<Blob> => {
  const response = await apiClient.get(`${PROPOSALS_BASE}/${proposalId}/pdf`, {
    responseType: 'blob',
  });
  return response.data;
};

/**
 * List attachments for a proposal (staff side).
 *
 * The backend returns a paginated envelope ``{items: [...], total: N}``
 * (FastAPI's AttachmentListResponse), not a bare array — unwrap to the
 * shape the caller expects. Without this, the React Query cache
 * resolves to the envelope object and ``attachments.length`` returns
 * undefined, so neither the empty-state nor the file list ever
 * renders even though the upload mutation succeeded.
 *
 * Shape validation (instead of a defensive ``?? []`` fallback): if
 * the backend ever serves a 200 with a different envelope (legacy
 * shape, misrouted endpoint, auth-redirect HTML 200, schema rename),
 * throw with a clear message so React Query exposes it via the
 * ``error`` branch in ProposalAttachmentsCard. ``?? []`` would mask
 * the regression as "empty list" indistinguishably from the real
 * empty case — exactly the failure mode the original bug had.
 */
export const listProposalAttachments = async (
  proposalId: number,
): Promise<ProposalAttachment[]> => {
  const response = await apiClient.get<{ items?: unknown; total?: unknown }>(
    `${PROPOSALS_BASE}/${proposalId}/attachments`,
  );
  const data = response.data;
  if (!data || typeof data !== 'object' || !Array.isArray(data.items)) {
    throw new Error('Unexpected proposal attachments response shape');
  }
  return data.items as ProposalAttachment[];
};

/**
 * Upload a PDF attachment for a proposal (staff side).
 */
export const uploadProposalAttachment = async (
  proposalId: number,
  file: File,
): Promise<ProposalAttachment> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post<ProposalAttachment>(
    `${PROPOSALS_BASE}/${proposalId}/attachments`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return response.data;
};

/**
 * Delete a proposal attachment (staff side; refused once proposal is signed).
 */
export const deleteProposalAttachment = async (
  proposalId: number,
  attachmentId: number,
): Promise<void> => {
  await apiClient.delete(
    `${PROPOSALS_BASE}/${proposalId}/attachments/${attachmentId}`,
  );
};

/**
 * Open a staff-side preview of a proposal attachment in a new browser tab.
 *
 * The attachment download endpoint requires bearer auth, so a plain
 * ``window.open(url)`` of the API URL would 401 — the bearer header
 * never reaches the new tab. Fetch the file as a blob through the
 * authenticated apiClient, mint an object URL, then open that. The
 * URL is revoked after a short delay so memory doesn't leak when the
 * user opens many attachments in a single session, and long enough
 * for the new tab's PDF viewer to actually load the bytes.
 *
 * Returns a promise that resolves once the new tab has been opened.
 */
export const openProposalAttachmentPreview = async (
  attachmentId: number,
): Promise<void> => {
  // Ask the backend for the presigned R2 URL as JSON instead of letting
  // XHR follow the 307 redirect to R2 — Cloudflare R2 doesn't return CORS
  // headers, so the browser blocks the redirect in the XHR path even
  // though it works fine for top-level navigation. Open the URL directly
  // with window.open below; the new tab navigates to R2 as a top-level
  // request and CORS doesn't apply.
  const response = await apiClient.get<{ download_url?: string }>(
    `/api/attachments/${attachmentId}/download`,
    { params: { as_json: 1 } },
  );
  const url = response.data?.download_url;
  if (!url) {
    // Empty response means the backend couldn't presign (R2 outage /
    // mis-config / unexpected boto3 exception) — without this guard
    // window.open('') silently pops about:blank with no diagnostic.
    throw new Error('Preview unavailable — could not load attachment URL');
  }
  // noopener/noreferrer keeps the new tab from accessing window.opener
  // (the staff CRM session). Per OWASP guidance for any user-content link.
  const opened = window.open(url, '_blank', 'noopener,noreferrer');
  if (!opened) {
    throw new Error('Popup blocked — allow popups to preview attachments');
  }
};

/**
 * URL for the public download endpoint that 302-redirects to a presigned R2
 * URL. Hitting it records the view as a side effect, which is why the public
 * page opens it in a new tab rather than fetching it as JSON.
 *
 * Reads VITE_API_URL directly instead of going through `apiClient.defaults`
 * so the public proposal page (which imports this helper) doesn't pull the
 * authenticated axios instance — that instance attaches the staff Bearer
 * token and would 401-evict the staff session if a customer's link
 * happened to be opened in the same browser.
 */
export const publicProposalAttachmentDownloadUrl = (
  token: string,
  attachmentId: number,
): string => {
  const baseUrl = import.meta.env.VITE_API_URL || '';
  return `${baseUrl}${PROPOSALS_BASE}/public/${token}/attachments/${attachmentId}/download`;
};

/**
 * Duplicate a proposal as a new draft with " (copy)" title suffix.
 */
export const duplicateProposal = async (proposalId: number): Promise<Proposal> => {
  const response = await apiClient.post<Proposal>(
    `${PROPOSALS_BASE}/${proposalId}/duplicate`,
  );
  return response.data;
};

/**
 * Fetch the raw bytes of the master service-agreement PDF.
 *
 * Streams through the backend (rather than redirecting to an R2
 * presigned URL) so the bearer-auth check runs and pdf.js gets a
 * same-origin Blob — Cloudflare R2 returns no CORS headers for
 * cross-origin XHRs.
 */
/**
 * Hard cap on a master service-agreement PDF upload. Mirrors the
 * backend's 25 MB limit so the client can fail-fast before the
 * multipart POST instead of round-tripping to the 413. Update both
 * sides together if ops ever bumps the cap.
 */
export const PROPOSAL_MASTER_CONTRACT_MAX_BYTES = 25 * 1024 * 1024;

export const listProposalSigningDocuments = async (
  proposalId: number,
): Promise<ProposalSigningDocument[]> => {
  const response = await apiClient.get<ProposalSigningDocument[]>(
    `${PROPOSALS_BASE}/${proposalId}/signing-documents`,
  );
  return response.data;
};

export const uploadProposalSigningDocument = async (
  proposalId: number,
  file: File,
): Promise<ProposalSigningDocument> => {
  const form = new FormData();
  form.append('file', file);
  const response = await apiClient.post<ProposalSigningDocument>(
    `${PROPOSALS_BASE}/${proposalId}/signing-documents`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return response.data;
};

export const updateProposalSigningDocument = async (
  proposalId: number,
  documentId: number,
  placements: {
    signature_field_coords?: SignatureFieldCoordsValue | null;
    date_field_coords?: SignatureFieldCoordsValue | null;
  },
): Promise<ProposalSigningDocument> => {
  const response = await apiClient.patch<ProposalSigningDocument>(
    `${PROPOSALS_BASE}/${proposalId}/signing-documents/${documentId}`,
    placements,
  );
  return response.data;
};

export const deleteProposalSigningDocument = async (
  proposalId: number,
  documentId: number,
): Promise<void> => {
  await apiClient.delete(
    `${PROPOSALS_BASE}/${proposalId}/signing-documents/${documentId}`,
  );
};

export const downloadProposalSigningDocument = async (
  proposalId: number,
  documentId: number,
): Promise<Blob> => {
  const response = await apiClient.get(
    `${PROPOSALS_BASE}/${proposalId}/signing-documents/${documentId}/pdf`,
    { responseType: 'blob' },
  );
  return response.data;
};

export const downloadProposalSigningDocumentSignedPdf = async (
  proposalId: number,
  documentId: number,
): Promise<Blob> => {
  const response = await apiClient.get(
    `${PROPOSALS_BASE}/${proposalId}/signing-documents/${documentId}/signed-pdf`,
    { responseType: 'blob' },
  );
  return response.data;
};

export const downloadProposalMasterContract = async (
  proposalId: number,
): Promise<Blob> => {
  const response = await apiClient.get(
    `${PROPOSALS_BASE}/${proposalId}/master-contract`,
    { responseType: 'blob' },
  );
  return response.data;
};

/**
 * Fetch the stamped signed-copy PDF bytes (master contract + signature
 * overlay + audit page). Returns 404 if the proposal isn't signed yet
 * or the accept-time stamper fail-softed without producing a copy —
 * the caller should surface that to the user so they can re-stamp.
 */
export const downloadProposalSignedPdf = async (
  proposalId: number,
): Promise<Blob> => {
  const response = await apiClient.get(
    `${PROPOSALS_BASE}/${proposalId}/signed-pdf`,
    { responseType: 'blob' },
  );
  return response.data;
};

/**
 * Fetch the captured e-signature PNG bytes for the audit trail. Returns
 * 404 when no signature was captured (unsigned, or rep-side admin-accept).
 */
export const downloadProposalSignatureImage = async (
  proposalId: number,
): Promise<Blob> => {
  const response = await apiClient.get(
    `${PROPOSALS_BASE}/${proposalId}/signature`,
    { responseType: 'blob' },
  );
  return response.data;
};

/**
 * Upload (or replace) a master service agreement PDF on a proposal.
 *
 * Used by the create flow to land a stashed file after
 * ``createProposalMutation`` resolves with the new id, and by the
 * detail-page sidebar to replace the master after the fact. PDF-only
 * and 25 MB cap enforced server-side; client-side checks live in the
 * picker components.
 */
export const uploadProposalMasterContract = async (
  proposalId: number,
  file: File,
): Promise<Proposal> => {
  const form = new FormData();
  form.append('file', file);
  const response = await apiClient.post<Proposal>(
    `${PROPOSALS_BASE}/${proposalId}/master-contract`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return response.data;
};

// ``refreshProposalFromQuote`` removed 2026-05-14 — quotes router
// unmounted; corresponding endpoint dropped from the backend.

export const proposalsApi = {
  list: listProposals,
  get: getProposal,
  create: createProposal,
  update: updateProposal,
  delete: deleteProposal,
  send: sendProposal,
  sendWithEmail: sendProposalWithEmail,
  accept: acceptProposal,
  createBundle: createProposalBundle,
  getBundle: getProposalBundle,
  updateBundle: updateProposalBundle,
  sendBundle: sendProposalBundle,
  removeBundleOption: removeProposalBundleOption,
  reject: rejectProposal,
  restampSignedPdf: restampProposalSignedPdf,
  listTemplates: listProposalTemplates,
  createTemplate: createProposalTemplate,
  getTemplate: getProposalTemplate,
  updateTemplate: updateProposalTemplate,
  deleteTemplate: deleteProposalTemplate,
  createFromTemplate: createFromTemplate,
  downloadPDF: downloadProposalPDF,
  listAttachments: listProposalAttachments,
  uploadAttachment: uploadProposalAttachment,
  deleteAttachment: deleteProposalAttachment,
  publicAttachmentDownloadUrl: publicProposalAttachmentDownloadUrl,
  duplicate: duplicateProposal,
  listSigningDocuments: listProposalSigningDocuments,
  uploadSigningDocument: uploadProposalSigningDocument,
  updateSigningDocument: updateProposalSigningDocument,
  deleteSigningDocument: deleteProposalSigningDocument,
  downloadSigningDocument: downloadProposalSigningDocument,
  downloadSigningDocumentSignedPdf: downloadProposalSigningDocumentSignedPdf,
  downloadMasterContract: downloadProposalMasterContract,
  downloadSignedPdf: downloadProposalSignedPdf,
  uploadMasterContract: uploadProposalMasterContract,
};

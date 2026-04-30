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
  AIGenerateProposalRequest,
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
 * Accept a proposal
 */
export const acceptProposal = async (proposalId: number): Promise<Proposal> => {
  const response = await apiClient.post<Proposal>(`${PROPOSALS_BASE}/${proposalId}/accept`);
  return response.data;
};

/**
 * Reject a proposal
 */
export const rejectProposal = async (proposalId: number): Promise<Proposal> => {
  const response = await apiClient.post<Proposal>(`${PROPOSALS_BASE}/${proposalId}/reject`);
  return response.data;
};

export interface ResendPaymentLinkResult {
  action: 'resent' | 'already_paid_reconciled';
  stripe_invoice_id?: string;
  hosted_invoice_url?: string | null;
}

export const resendProposalPaymentLink = async (
  proposalId: number,
): Promise<ResendPaymentLinkResult> => {
  const response = await apiClient.post<ResendPaymentLinkResult>(
    `${PROPOSALS_BASE}/${proposalId}/resend-payment-link`,
  );
  return response.data;
};

/**
 * Re-run Stripe billing spawn for a proposal whose initial spawn failed.
 * Refuses if the proposal already has any Stripe artifact.
 */
export const retryProposalBilling = async (proposalId: number): Promise<Proposal> => {
  const response = await apiClient.post<Proposal>(
    `${PROPOSALS_BASE}/${proposalId}/retry-billing`,
  );
  return response.data;
};

/**
 * Generate a proposal using AI
 */
export const generateProposal = async (data: AIGenerateProposalRequest): Promise<Proposal> => {
  const response = await apiClient.post<Proposal>(`${PROPOSALS_BASE}/generate`, data);
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

export const proposalsApi = {
  list: listProposals,
  get: getProposal,
  create: createProposal,
  update: updateProposal,
  delete: deleteProposal,
  send: sendProposal,
  sendWithEmail: sendProposalWithEmail,
  accept: acceptProposal,
  reject: rejectProposal,
  resendPaymentLink: resendProposalPaymentLink,
  retryBilling: retryProposalBilling,
  generate: generateProposal,
  listTemplates: listProposalTemplates,
  createTemplate: createProposalTemplate,
  getTemplate: getProposalTemplate,
  updateTemplate: updateProposalTemplate,
  deleteTemplate: deleteProposalTemplate,
  createFromTemplate: createFromTemplate,
  downloadPDF: downloadProposalPDF,
};


/**
 * Campaigns API
 */

import { apiClient } from './client';
import type {
  Campaign,
  CampaignCreate,
  CampaignUpdate,
  CampaignListResponse,
  CampaignFilters,
  CampaignMember,
  CampaignMemberUpdate,
  CampaignStats,
  AddMembersRequest,
  AddMembersResponse,
  EmailTemplate,
  EmailTemplateCreate,
  EmailTemplateUpdate,
  EmailCampaignStep,
  EmailCampaignStepCreate,
  EmailCampaignStepUpdate,
} from '../types';

const CAMPAIGNS_BASE = '/api/campaigns';

// =============================================================================
// Campaigns CRUD
// =============================================================================

/**
 * List campaigns with pagination and filters
 */
export const listCampaigns = async (
  filters: CampaignFilters = {}
): Promise<CampaignListResponse> => {
  const response = await apiClient.get<CampaignListResponse>(CAMPAIGNS_BASE, {
    params: filters,
  });
  return response.data;
};

/**
 * Get a campaign by ID
 */
export const getCampaign = async (campaignId: number): Promise<Campaign> => {
  const response = await apiClient.get<Campaign>(`${CAMPAIGNS_BASE}/${campaignId}`);
  return response.data;
};

/**
 * Create a new campaign
 */
export const createCampaign = async (campaignData: CampaignCreate): Promise<Campaign> => {
  const response = await apiClient.post<Campaign>(CAMPAIGNS_BASE, campaignData);
  return response.data;
};

/**
 * Update a campaign
 */
export const updateCampaign = async (
  campaignId: number,
  campaignData: CampaignUpdate
): Promise<Campaign> => {
  const response = await apiClient.patch<Campaign>(
    `${CAMPAIGNS_BASE}/${campaignId}`,
    campaignData
  );
  return response.data;
};

/**
 * Delete a campaign
 */
export const deleteCampaign = async (campaignId: number): Promise<void> => {
  await apiClient.delete(`${CAMPAIGNS_BASE}/${campaignId}`);
};

/**
 * Get campaign statistics
 */
export const getCampaignStats = async (campaignId: number): Promise<CampaignStats> => {
  const response = await apiClient.get<CampaignStats>(
    `${CAMPAIGNS_BASE}/${campaignId}/stats`
  );
  return response.data;
};

// =============================================================================
// Campaign Members
// =============================================================================

/**
 * List members of a campaign
 */
export const getCampaignMembers = async (
  campaignId: number,
  params?: { page?: number; page_size?: number; status?: string }
): Promise<CampaignMember[]> => {
  const response = await apiClient.get<CampaignMember[]>(
    `${CAMPAIGNS_BASE}/${campaignId}/members`,
    { params }
  );
  return response.data;
};

/**
 * Add members to a campaign
 */
export const addCampaignMembers = async (
  campaignId: number,
  data: AddMembersRequest
): Promise<AddMembersResponse> => {
  const response = await apiClient.post<AddMembersResponse>(
    `${CAMPAIGNS_BASE}/${campaignId}/members`,
    data
  );
  return response.data;
};

/**
 * Update a campaign member
 */
export const updateCampaignMember = async (
  campaignId: number,
  memberId: number,
  data: CampaignMemberUpdate
): Promise<CampaignMember> => {
  const response = await apiClient.patch<CampaignMember>(
    `${CAMPAIGNS_BASE}/${campaignId}/members/${memberId}`,
    data
  );
  return response.data;
};

/**
 * Remove a member from a campaign
 */
export const removeCampaignMember = async (
  campaignId: number,
  memberId: number
): Promise<void> => {
  await apiClient.delete(`${CAMPAIGNS_BASE}/${campaignId}/members/${memberId}`);
};

// =============================================================================
// Email Templates
// =============================================================================

export const listEmailTemplates = async (
  params?: { page?: number; page_size?: number; category?: string }
): Promise<EmailTemplate[]> => {
  const response = await apiClient.get<EmailTemplate[]>(`${CAMPAIGNS_BASE}/templates`, { params });
  return response.data;
};

export const getEmailTemplate = async (templateId: number): Promise<EmailTemplate> => {
  const response = await apiClient.get<EmailTemplate>(`${CAMPAIGNS_BASE}/templates/${templateId}`);
  return response.data;
};

export const createEmailTemplate = async (data: EmailTemplateCreate): Promise<EmailTemplate> => {
  const response = await apiClient.post<EmailTemplate>(`${CAMPAIGNS_BASE}/templates`, data);
  return response.data;
};

export const updateEmailTemplate = async (
  templateId: number,
  data: EmailTemplateUpdate
): Promise<EmailTemplate> => {
  const response = await apiClient.put<EmailTemplate>(
    `${CAMPAIGNS_BASE}/templates/${templateId}`,
    data
  );
  return response.data;
};

export const deleteEmailTemplate = async (templateId: number): Promise<void> => {
  await apiClient.delete(`${CAMPAIGNS_BASE}/templates/${templateId}`);
};

// =============================================================================
// Campaign Steps
// =============================================================================

export const getCampaignSteps = async (campaignId: number): Promise<EmailCampaignStep[]> => {
  const response = await apiClient.get<EmailCampaignStep[]>(
    `${CAMPAIGNS_BASE}/${campaignId}/steps`
  );
  return response.data;
};

export const addCampaignStep = async (
  campaignId: number,
  data: EmailCampaignStepCreate
): Promise<EmailCampaignStep> => {
  const response = await apiClient.post<EmailCampaignStep>(
    `${CAMPAIGNS_BASE}/${campaignId}/steps`,
    data
  );
  return response.data;
};

export const updateCampaignStep = async (
  campaignId: number,
  stepId: number,
  data: EmailCampaignStepUpdate
): Promise<EmailCampaignStep> => {
  const response = await apiClient.put<EmailCampaignStep>(
    `${CAMPAIGNS_BASE}/${campaignId}/steps/${stepId}`,
    data
  );
  return response.data;
};

export const deleteCampaignStep = async (
  campaignId: number,
  stepId: number
): Promise<void> => {
  await apiClient.delete(`${CAMPAIGNS_BASE}/${campaignId}/steps/${stepId}`);
};

export const executeCampaign = async (
  campaignId: number
): Promise<{ message: string; status: string }> => {
  const response = await apiClient.post(`${CAMPAIGNS_BASE}/${campaignId}/execute`);
  return response.data;
};

// Export all campaign functions
export const campaignsApi = {
  // CRUD
  list: listCampaigns,
  get: getCampaign,
  create: createCampaign,
  update: updateCampaign,
  delete: deleteCampaign,
  getStats: getCampaignStats,
  // Members
  getMembers: getCampaignMembers,
  addMembers: addCampaignMembers,
  updateMember: updateCampaignMember,
  removeMember: removeCampaignMember,
  // Templates
  listTemplates: listEmailTemplates,
  getTemplate: getEmailTemplate,
  createTemplate: createEmailTemplate,
  updateTemplate: updateEmailTemplate,
  deleteTemplate: deleteEmailTemplate,
  // Steps
  getSteps: getCampaignSteps,
  addStep: addCampaignStep,
  updateStep: updateCampaignStep,
  deleteStep: deleteCampaignStep,
  // Execute
  execute: executeCampaign,
};

export default campaignsApi;

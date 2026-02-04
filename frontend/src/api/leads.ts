/**
 * Leads API
 */

import { apiClient } from './client';
import type {
  Lead,
  LeadCreate,
  LeadUpdate,
  LeadListResponse,
  LeadFilters,
  LeadSource,
  LeadSourceCreate,
  LeadConvertToContactRequest,
  LeadConvertToOpportunityRequest,
  LeadFullConversionRequest,
  ConversionResponse,
} from '../types';

const LEADS_BASE = '/api/leads';

/**
 * List leads with pagination and filters
 */
export const listLeads = async (filters: LeadFilters = {}): Promise<LeadListResponse> => {
  const response = await apiClient.get<LeadListResponse>(LEADS_BASE, {
    params: filters,
  });
  return response.data;
};

/**
 * Get a lead by ID
 */
export const getLead = async (leadId: number): Promise<Lead> => {
  const response = await apiClient.get<Lead>(`${LEADS_BASE}/${leadId}`);
  return response.data;
};

/**
 * Create a new lead
 */
export const createLead = async (leadData: LeadCreate): Promise<Lead> => {
  const response = await apiClient.post<Lead>(LEADS_BASE, leadData);
  return response.data;
};

/**
 * Update a lead
 */
export const updateLead = async (
  leadId: number,
  leadData: LeadUpdate
): Promise<Lead> => {
  const response = await apiClient.patch<Lead>(`${LEADS_BASE}/${leadId}`, leadData);
  return response.data;
};

/**
 * Delete a lead
 */
export const deleteLead = async (leadId: number): Promise<void> => {
  await apiClient.delete(`${LEADS_BASE}/${leadId}`);
};

// =============================================================================
// Lead Sources
// =============================================================================

/**
 * List all lead sources
 */
export const listLeadSources = async (activeOnly = true): Promise<LeadSource[]> => {
  const response = await apiClient.get<LeadSource[]>(`${LEADS_BASE}/sources/`, {
    params: { active_only: activeOnly },
  });
  return response.data;
};

/**
 * Create a new lead source
 */
export const createLeadSource = async (sourceData: LeadSourceCreate): Promise<LeadSource> => {
  const response = await apiClient.post<LeadSource>(`${LEADS_BASE}/sources/`, sourceData);
  return response.data;
};

// =============================================================================
// Lead Conversion
// =============================================================================

/**
 * Convert a lead to a contact
 */
export const convertToContact = async (
  leadId: number,
  request: LeadConvertToContactRequest
): Promise<ConversionResponse> => {
  const response = await apiClient.post<ConversionResponse>(
    `${LEADS_BASE}/${leadId}/convert/contact`,
    request
  );
  return response.data;
};

/**
 * Convert a lead to an opportunity
 */
export const convertToOpportunity = async (
  leadId: number,
  request: LeadConvertToOpportunityRequest
): Promise<ConversionResponse> => {
  const response = await apiClient.post<ConversionResponse>(
    `${LEADS_BASE}/${leadId}/convert/opportunity`,
    request
  );
  return response.data;
};

/**
 * Full lead conversion: Lead -> Contact + Company + Opportunity
 */
export const fullConversion = async (
  leadId: number,
  request: LeadFullConversionRequest
): Promise<ConversionResponse> => {
  const response = await apiClient.post<ConversionResponse>(
    `${LEADS_BASE}/${leadId}/convert/full`,
    request
  );
  return response.data;
};

// Export all lead functions
export const leadsApi = {
  list: listLeads,
  get: getLead,
  create: createLead,
  update: updateLead,
  delete: deleteLead,
  // Sources
  listSources: listLeadSources,
  createSource: createLeadSource,
  // Conversion
  convertToContact,
  convertToOpportunity,
  fullConversion,
};

export default leadsApi;

/**
 * Companies API
 */

import { apiClient } from './client';
import type {
  Company,
  CompanyCreate,
  CompanyUpdate,
  CompanyListResponse,
  CompanyFilters,
} from '../types';

const COMPANIES_BASE = '/api/companies';

/**
 * List companies with pagination and filters
 */
export const listCompanies = async (filters: CompanyFilters = {}): Promise<CompanyListResponse> => {
  const response = await apiClient.get<CompanyListResponse>(COMPANIES_BASE, {
    params: filters,
  });
  return response.data;
};

/**
 * Get a company by ID
 */
export const getCompany = async (companyId: number): Promise<Company> => {
  const response = await apiClient.get<Company>(`${COMPANIES_BASE}/${companyId}`);
  return response.data;
};

/**
 * Create a new company
 */
export const createCompany = async (companyData: CompanyCreate): Promise<Company> => {
  const response = await apiClient.post<Company>(COMPANIES_BASE, companyData);
  return response.data;
};

/**
 * Update a company
 */
export const updateCompany = async (
  companyId: number,
  companyData: CompanyUpdate
): Promise<Company> => {
  const response = await apiClient.patch<Company>(
    `${COMPANIES_BASE}/${companyId}`,
    companyData
  );
  return response.data;
};

/**
 * Delete a company
 */
export const deleteCompany = async (companyId: number): Promise<void> => {
  await apiClient.delete(`${COMPANIES_BASE}/${companyId}`);
};

// Export all company functions
export const companiesApi = {
  list: listCompanies,
  get: getCompany,
  create: createCompany,
  update: updateCompany,
  delete: deleteCompany,
};

export default companiesApi;

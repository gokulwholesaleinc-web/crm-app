/**
 * Contracts API
 */

import { apiClient } from './client';
import type {
  Contract,
  ContractCreate,
  ContractUpdate,
  ContractListResponse,
  ContractFilters,
  ContractStats,
} from '../types';

const CONTRACTS_BASE = '/api/contracts';

/**
 * List contracts with pagination and filters
 */
export const listContracts = async (
  filters: ContractFilters = {}
): Promise<ContractListResponse> => {
  const response = await apiClient.get<ContractListResponse>(CONTRACTS_BASE, {
    params: filters,
  });
  return response.data;
};

/**
 * Get a contract by ID
 */
export const getContract = async (contractId: number): Promise<Contract> => {
  const response = await apiClient.get<Contract>(
    `${CONTRACTS_BASE}/${contractId}`
  );
  return response.data;
};

/**
 * Create a new contract
 */
export const createContract = async (
  contractData: ContractCreate
): Promise<Contract> => {
  const response = await apiClient.post<Contract>(CONTRACTS_BASE, contractData);
  return response.data;
};

/**
 * Update a contract
 */
export const updateContract = async (
  contractId: number,
  contractData: ContractUpdate
): Promise<Contract> => {
  const response = await apiClient.patch<Contract>(
    `${CONTRACTS_BASE}/${contractId}`,
    contractData
  );
  return response.data;
};

/**
 * Delete a contract
 */
export const deleteContract = async (contractId: number): Promise<void> => {
  await apiClient.delete(`${CONTRACTS_BASE}/${contractId}`);
};

/**
 * Send contract for signature
 */
export const sendContract = async (
  contractId: number,
  body: { to_email?: string; message?: string } = {}
): Promise<{ id: number; status: string; sent_at: string; sign_url: string; sign_token_expires_at: string }> => {
  const response = await apiClient.post(
    `${CONTRACTS_BASE}/${contractId}/send`,
    body
  );
  return response.data;
};

/**
 * Get contract aggregate stats
 */
export const getContractStats = async (): Promise<ContractStats> => {
  const response = await apiClient.get<ContractStats>(`${CONTRACTS_BASE}/stats`);
  return response.data;
};

export const contractsApi = {
  list: listContracts,
  get: getContract,
  create: createContract,
  update: updateContract,
  delete: deleteContract,
  send: sendContract,
  stats: getContractStats,
};


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

export const contractsApi = {
  list: listContracts,
  get: getContract,
  create: createContract,
  update: updateContract,
  delete: deleteContract,
};

export default contractsApi;

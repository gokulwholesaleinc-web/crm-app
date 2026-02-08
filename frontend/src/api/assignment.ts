/**
 * Assignment Rules API
 */

import { apiClient } from './client';
import type {
  AssignmentRule,
  AssignmentRuleCreate,
  AssignmentRuleUpdate,
  AssignmentStats,
} from '../types';

const BASE = '/api/assignment-rules';

export const listAssignmentRules = async (): Promise<AssignmentRule[]> => {
  const response = await apiClient.get<AssignmentRule[]>(BASE);
  return response.data;
};

export const getAssignmentRule = async (id: number): Promise<AssignmentRule> => {
  const response = await apiClient.get<AssignmentRule>(`${BASE}/${id}`);
  return response.data;
};

export const createAssignmentRule = async (
  data: AssignmentRuleCreate
): Promise<AssignmentRule> => {
  const response = await apiClient.post<AssignmentRule>(BASE, data);
  return response.data;
};

export const updateAssignmentRule = async (
  id: number,
  data: AssignmentRuleUpdate
): Promise<AssignmentRule> => {
  const response = await apiClient.put<AssignmentRule>(`${BASE}/${id}`, data);
  return response.data;
};

export const deleteAssignmentRule = async (id: number): Promise<void> => {
  await apiClient.delete(`${BASE}/${id}`);
};

export const getAssignmentStats = async (
  id: number
): Promise<AssignmentStats[]> => {
  const response = await apiClient.get<AssignmentStats[]>(
    `${BASE}/${id}/stats`
  );
  return response.data;
};

export const assignmentApi = {
  list: listAssignmentRules,
  get: getAssignmentRule,
  create: createAssignmentRule,
  update: updateAssignmentRule,
  delete: deleteAssignmentRule,
  getStats: getAssignmentStats,
};

export default assignmentApi;

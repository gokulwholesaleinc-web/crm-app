/**
 * Workflows API
 */

import { apiClient } from './client';
import type {
  WorkflowRule,
  WorkflowRuleCreate,
  WorkflowRuleUpdate,
  WorkflowExecution,
  WorkflowTestRequest,
} from '../types';

const WORKFLOWS_BASE = '/api/workflows';

export const listWorkflowRules = async (
  params?: { page?: number; page_size?: number; is_active?: boolean; trigger_entity?: string }
): Promise<WorkflowRule[]> => {
  const response = await apiClient.get<WorkflowRule[]>(WORKFLOWS_BASE, { params });
  return response.data;
};

export const getWorkflowRule = async (ruleId: number): Promise<WorkflowRule> => {
  const response = await apiClient.get<WorkflowRule>(`${WORKFLOWS_BASE}/${ruleId}`);
  return response.data;
};

export const createWorkflowRule = async (data: WorkflowRuleCreate): Promise<WorkflowRule> => {
  const response = await apiClient.post<WorkflowRule>(WORKFLOWS_BASE, data);
  return response.data;
};

export const updateWorkflowRule = async (
  ruleId: number,
  data: WorkflowRuleUpdate
): Promise<WorkflowRule> => {
  const response = await apiClient.put<WorkflowRule>(`${WORKFLOWS_BASE}/${ruleId}`, data);
  return response.data;
};

export const deleteWorkflowRule = async (ruleId: number): Promise<void> => {
  await apiClient.delete(`${WORKFLOWS_BASE}/${ruleId}`);
};

export const getWorkflowExecutions = async (
  ruleId: number,
  params?: { page?: number; page_size?: number }
): Promise<WorkflowExecution[]> => {
  const response = await apiClient.get<WorkflowExecution[]>(
    `${WORKFLOWS_BASE}/${ruleId}/executions`,
    { params }
  );
  return response.data;
};

export const testWorkflowRule = async (
  ruleId: number,
  data: WorkflowTestRequest
): Promise<{ rule_id: number; dry_run: boolean; results: unknown[] }> => {
  const response = await apiClient.post(`${WORKFLOWS_BASE}/${ruleId}/test`, data);
  return response.data;
};

export const workflowsApi = {
  list: listWorkflowRules,
  get: getWorkflowRule,
  create: createWorkflowRule,
  update: updateWorkflowRule,
  delete: deleteWorkflowRule,
  getExecutions: getWorkflowExecutions,
  test: testWorkflowRule,
};

export default workflowsApi;

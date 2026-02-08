/**
 * Sequences API
 */

import { apiClient } from './client';
import type {
  Sequence,
  SequenceCreate,
  SequenceUpdate,
  SequenceEnrollment,
  ProcessDueResult,
} from '../types';

const BASE = '/api/sequences';

export const listSequences = async (): Promise<Sequence[]> => {
  const response = await apiClient.get<Sequence[]>(BASE);
  return response.data;
};

export const getSequence = async (id: number): Promise<Sequence> => {
  const response = await apiClient.get<Sequence>(`${BASE}/${id}`);
  return response.data;
};

export const createSequence = async (data: SequenceCreate): Promise<Sequence> => {
  const response = await apiClient.post<Sequence>(BASE, data);
  return response.data;
};

export const updateSequence = async (
  id: number,
  data: SequenceUpdate
): Promise<Sequence> => {
  const response = await apiClient.put<Sequence>(`${BASE}/${id}`, data);
  return response.data;
};

export const deleteSequence = async (id: number): Promise<void> => {
  await apiClient.delete(`${BASE}/${id}`);
};

export const enrollContact = async (
  sequenceId: number,
  contactId: number
): Promise<SequenceEnrollment> => {
  const response = await apiClient.post<SequenceEnrollment>(
    `${BASE}/${sequenceId}/enroll`,
    { contact_id: contactId }
  );
  return response.data;
};

export const getEnrollments = async (
  sequenceId: number
): Promise<SequenceEnrollment[]> => {
  const response = await apiClient.get<SequenceEnrollment[]>(
    `${BASE}/${sequenceId}/enrollments`
  );
  return response.data;
};

export const pauseEnrollment = async (
  enrollmentId: number
): Promise<SequenceEnrollment> => {
  const response = await apiClient.put<SequenceEnrollment>(
    `${BASE}/enrollments/${enrollmentId}/pause`
  );
  return response.data;
};

export const resumeEnrollment = async (
  enrollmentId: number
): Promise<SequenceEnrollment> => {
  const response = await apiClient.put<SequenceEnrollment>(
    `${BASE}/enrollments/${enrollmentId}/resume`
  );
  return response.data;
};

export const processDueSteps = async (): Promise<ProcessDueResult> => {
  const response = await apiClient.post<ProcessDueResult>(`${BASE}/process-due`);
  return response.data;
};

export const getContactEnrollments = async (
  contactId: number
): Promise<SequenceEnrollment[]> => {
  const response = await apiClient.get<SequenceEnrollment[]>(
    `${BASE}/contacts/${contactId}/enrollments`
  );
  return response.data;
};

export const sequencesApi = {
  list: listSequences,
  get: getSequence,
  create: createSequence,
  update: updateSequence,
  delete: deleteSequence,
  enrollContact,
  getEnrollments,
  pauseEnrollment,
  resumeEnrollment,
  processDueSteps,
  getContactEnrollments,
};

export default sequencesApi;

/**
 * Sequences hooks using TanStack Query.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { sequencesApi } from '../api/sequences';
import { useAuthQuery } from './useAuthQuery';
import type { SequenceCreate, SequenceUpdate } from '../types';

export const sequenceKeys = {
  all: ['sequences'] as const,
  lists: () => ['sequences', 'list'] as const,
  details: () => ['sequences', 'detail'] as const,
  detail: (id: number) => ['sequences', 'detail', id] as const,
  enrollments: (id: number) => ['sequences', 'enrollments', id] as const,
  contactEnrollments: (contactId: number) =>
    ['sequences', 'contact-enrollments', contactId] as const,
};

export function useSequences() {
  return useAuthQuery({
    queryKey: sequenceKeys.lists(),
    queryFn: () => sequencesApi.list(),
  });
}

export function useSequence(id: number | undefined) {
  return useAuthQuery({
    queryKey: sequenceKeys.detail(id!),
    queryFn: () => sequencesApi.get(id!),
    enabled: !!id,
  });
}

export function useSequenceEnrollments(id: number | undefined) {
  return useAuthQuery({
    queryKey: sequenceKeys.enrollments(id!),
    queryFn: () => sequencesApi.getEnrollments(id!),
    enabled: !!id,
  });
}

export function useContactEnrollments(contactId: number | undefined) {
  return useAuthQuery({
    queryKey: sequenceKeys.contactEnrollments(contactId!),
    queryFn: () => sequencesApi.getContactEnrollments(contactId!),
    enabled: !!contactId,
  });
}

export function useCreateSequence() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SequenceCreate) => sequencesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sequenceKeys.lists() });
    },
  });
}

export function useUpdateSequence() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: SequenceUpdate }) =>
      sequencesApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: sequenceKeys.lists() });
      queryClient.invalidateQueries({ queryKey: sequenceKeys.detail(id) });
    },
  });
}

export function useDeleteSequence() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => sequencesApi.delete(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: sequenceKeys.lists() });
      queryClient.removeQueries({ queryKey: sequenceKeys.detail(id) });
    },
  });
}

export function useEnrollContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sequenceId, contactId }: { sequenceId: number; contactId: number }) =>
      sequencesApi.enrollContact(sequenceId, contactId),
    onSuccess: (_, { sequenceId }) => {
      queryClient.invalidateQueries({ queryKey: sequenceKeys.enrollments(sequenceId) });
    },
  });
}

export function usePauseEnrollment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (enrollmentId: number) => sequencesApi.pauseEnrollment(enrollmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sequenceKeys.all });
    },
  });
}

export function useResumeEnrollment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (enrollmentId: number) => sequencesApi.resumeEnrollment(enrollmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sequenceKeys.all });
    },
  });
}

export function useProcessDueSteps() {
  return useMutation({
    mutationFn: () => sequencesApi.processDueSteps(),
  });
}

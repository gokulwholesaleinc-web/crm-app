/**
 * Attachment hooks using TanStack Query.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthQuery } from './useAuthQuery';
import { attachmentsApi } from '../api/attachments';
import type { AttachmentResponse } from '../api/attachments';

export const attachmentKeys = {
  all: ['attachments'] as const,
  entity: (entityType: string, entityId: number) =>
    [...attachmentKeys.all, entityType, entityId] as const,
};

export function useAttachments(entityType: string, entityId: number) {
  return useAuthQuery({
    queryKey: attachmentKeys.entity(entityType, entityId),
    queryFn: () => attachmentsApi.list(entityType, entityId),
    enabled: !!entityType && !!entityId,
  });
}

export function useUploadAttachment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      file,
      entityType,
      entityId,
    }: {
      file: File;
      entityType: string;
      entityId: number;
    }) => attachmentsApi.upload(file, entityType, entityId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: attachmentKeys.entity(variables.entityType, variables.entityId),
      });
    },
  });
}

export function useDeleteAttachment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
    }: {
      id: number;
      entityType: string;
      entityId: number;
    }) => attachmentsApi.delete(id),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: attachmentKeys.entity(variables.entityType, variables.entityId),
      });
    },
  });
}

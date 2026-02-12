/**
 * Sharing hooks using TanStack Query.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthQuery } from './useAuthQuery';
import { sharingApi, ShareRequest } from '../api/sharing';

export const sharingKeys = {
  all: ['sharing'] as const,
  entity: (entityType: string, entityId: number) =>
    [...sharingKeys.all, entityType, entityId] as const,
};

export function useEntityShares(entityType: string, entityId: number) {
  return useAuthQuery({
    queryKey: sharingKeys.entity(entityType, entityId),
    queryFn: () => sharingApi.list(entityType, entityId),
    enabled: !!entityType && !!entityId,
  });
}

export function useShareEntity() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ShareRequest) => sharingApi.share(data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: sharingKeys.entity(variables.entity_type, variables.entity_id),
      });
    },
  });
}

export function useRevokeShare() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      shareId,
    }: {
      shareId: number;
      entityType: string;
      entityId: number;
    }) => sharingApi.revoke(shareId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: sharingKeys.entity(variables.entityType, variables.entityId),
      });
    },
  });
}

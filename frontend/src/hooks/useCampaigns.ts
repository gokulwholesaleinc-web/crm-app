/**
 * Campaigns hooks using TanStack Query
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { campaignsApi } from '../api/campaigns';
import type {
  CampaignCreate,
  CampaignUpdate,
  CampaignFilters,
  AddMembersRequest,
} from '../types';

// Query keys
export const campaignKeys = {
  all: ['campaigns'] as const,
  lists: () => [...campaignKeys.all, 'list'] as const,
  list: (filters?: CampaignFilters) => [...campaignKeys.lists(), filters] as const,
  details: () => [...campaignKeys.all, 'detail'] as const,
  detail: (id: number) => [...campaignKeys.details(), id] as const,
  stats: (id: number) => [...campaignKeys.all, 'stats', id] as const,
  members: (id: number, params?: { page?: number; page_size?: number; status?: string }) =>
    [...campaignKeys.all, 'members', id, params] as const,
};

/**
 * Hook to fetch a paginated list of campaigns
 */
export function useCampaigns(filters?: CampaignFilters) {
  return useQuery({
    queryKey: campaignKeys.list(filters),
    queryFn: () => campaignsApi.list(filters),
  });
}

/**
 * Hook to fetch a single campaign by ID
 */
export function useCampaign(id: number | undefined) {
  return useQuery({
    queryKey: campaignKeys.detail(id!),
    queryFn: () => campaignsApi.get(id!),
    enabled: !!id,
  });
}

/**
 * Hook to fetch campaign stats
 */
export function useCampaignStats(id: number | undefined) {
  return useQuery({
    queryKey: campaignKeys.stats(id!),
    queryFn: () => campaignsApi.getStats(id!),
    enabled: !!id,
  });
}

/**
 * Hook to fetch campaign members
 */
export function useCampaignMembers(
  id: number | undefined,
  params?: { page?: number; page_size?: number; status?: string }
) {
  return useQuery({
    queryKey: campaignKeys.members(id!, params),
    queryFn: () => campaignsApi.getMembers(id!, params),
    enabled: !!id,
  });
}

/**
 * Hook to create a new campaign
 */
export function useCreateCampaign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CampaignCreate) => campaignsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: campaignKeys.lists() });
    },
  });
}

/**
 * Hook to update a campaign
 */
export function useUpdateCampaign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: CampaignUpdate }) =>
      campaignsApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: campaignKeys.lists() });
      queryClient.invalidateQueries({ queryKey: campaignKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: campaignKeys.stats(id) });
    },
  });
}

/**
 * Hook to delete a campaign
 */
export function useDeleteCampaign() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => campaignsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: campaignKeys.lists() });
    },
  });
}

/**
 * Hook to add members to a campaign
 */
export function useAddCampaignMembers() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ campaignId, data }: { campaignId: number; data: AddMembersRequest }) =>
      campaignsApi.addMembers(campaignId, data),
    onSuccess: (_, { campaignId }) => {
      queryClient.invalidateQueries({ queryKey: campaignKeys.members(campaignId) });
      queryClient.invalidateQueries({ queryKey: campaignKeys.stats(campaignId) });
      queryClient.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
    },
  });
}

/**
 * Hook to remove a member from a campaign
 */
export function useRemoveCampaignMember() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ campaignId, memberId }: { campaignId: number; memberId: number }) =>
      campaignsApi.removeMember(campaignId, memberId),
    onSuccess: (_, { campaignId }) => {
      queryClient.invalidateQueries({ queryKey: campaignKeys.members(campaignId) });
      queryClient.invalidateQueries({ queryKey: campaignKeys.stats(campaignId) });
      queryClient.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
    },
  });
}

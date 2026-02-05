/**
 * Campaigns hooks using the entity CRUD factory pattern.
 * Uses TanStack Query for data fetching and caching.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createEntityHooks, createQueryKeys } from './useEntityCRUD';
import { campaignsApi } from '../api/campaigns';
import type {
  Campaign,
  CampaignCreate,
  CampaignUpdate,
  CampaignFilters,
  AddMembersRequest,
} from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const campaignKeys = {
  ...createQueryKeys('campaigns'),
  stats: (id: number) => ['campaigns', 'stats', id] as const,
  members: (id: number, params?: { page?: number; page_size?: number; status?: string }) =>
    ['campaigns', 'members', id, params] as const,
};

// =============================================================================
// Entity CRUD Hooks using Factory Pattern
// =============================================================================

const campaignEntityHooks = createEntityHooks<
  Campaign,
  CampaignCreate,
  CampaignUpdate,
  CampaignFilters
>({
  entityName: 'campaigns',
  baseUrl: '/api/campaigns',
  queryKey: 'campaigns',
});

/**
 * Hook to fetch a paginated list of campaigns
 */
export function useCampaigns(filters?: CampaignFilters) {
  return campaignEntityHooks.useList(filters);
}

/**
 * Hook to fetch a single campaign by ID
 */
export function useCampaign(id: number | undefined) {
  return campaignEntityHooks.useOne(id);
}

/**
 * Hook to create a new campaign
 */
export function useCreateCampaign() {
  return campaignEntityHooks.useCreate();
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
  return campaignEntityHooks.useDelete();
}

// =============================================================================
// Campaign Stats and Members Hooks
// =============================================================================

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

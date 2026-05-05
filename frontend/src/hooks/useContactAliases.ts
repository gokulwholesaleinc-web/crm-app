import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';

export interface ContactEmailAlias {
  id: number;
  contact_id: number;
  email: string;
  label: string | null;
  created_at: string;
}

interface AddAliasPayload {
  email: string;
  label?: string;
}

function aliasKeys(contactId: number) {
  return ['contacts', contactId, 'aliases'] as const;
}

export function useContactAliases(contactId: number | undefined) {
  return useQuery({
    queryKey: contactId ? aliasKeys(contactId) : ['contacts', 'aliases', 'noop'],
    queryFn: async () => {
      const res = await apiClient.get<ContactEmailAlias[]>(
        `/api/contacts/${contactId}/aliases`
      );
      return res.data;
    },
    enabled: contactId !== undefined,
  });
}

export function useAddAlias(contactId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: AddAliasPayload) => {
      const res = await apiClient.post<ContactEmailAlias>(
        `/api/contacts/${contactId}/aliases`,
        payload
      );
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: aliasKeys(contactId) });
    },
  });
}

export function useDeleteAlias(contactId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (aliasId: number) => {
      await apiClient.delete(`/api/contacts/${contactId}/aliases/${aliasId}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: aliasKeys(contactId) });
    },
  });
}

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getCompanyMeta, syncCompanyMeta, exportMetaCsv } from '../api/meta';

export const metaKeys = {
  all: ['meta'] as const,
  company: (companyId: number) => [...metaKeys.all, 'company', companyId] as const,
};

export function useCompanyMeta(companyId: number | undefined) {
  return useQuery({
    queryKey: metaKeys.company(companyId!),
    queryFn: () => getCompanyMeta(companyId!),
    enabled: !!companyId,
    retry: false,
  });
}

export function useSyncCompanyMeta() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ companyId, pageId }: { companyId: number; pageId: string }) =>
      syncCompanyMeta(companyId, pageId),
    onSuccess: (_, { companyId }) => {
      queryClient.invalidateQueries({ queryKey: metaKeys.company(companyId) });
    },
  });
}

export function useExportMetaCsv() {
  return useMutation({
    mutationFn: (companyId: number) => exportMetaCsv(companyId),
  });
}

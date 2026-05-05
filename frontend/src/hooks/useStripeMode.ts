import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';

interface StripeModeResponse {
  mode: 'live' | 'test' | 'unconfigured';
  publishable_hint: string | null;
}

async function fetchStripeMode(): Promise<StripeModeResponse> {
  const resp = await apiClient.get<StripeModeResponse>('/api/payments/mode');
  return resp.data;
}

export function useStripeMode() {
  const { data, isLoading } = useQuery({
    queryKey: ['stripe-mode'],
    queryFn: fetchStripeMode,
    staleTime: 60_000,
  });
  return { mode: data?.mode, isLoading };
}

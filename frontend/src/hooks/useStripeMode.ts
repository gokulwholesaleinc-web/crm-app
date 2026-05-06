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
  const { data, isLoading, isError } = useQuery({
    queryKey: ['stripe-mode'],
    queryFn: fetchStripeMode,
    staleTime: 60_000,
  });
  // Fail closed — if /api/payments/mode 5xx'd or 401'd the previous
  // shape returned `mode: undefined`, the SendInvoiceModal compared
  // strictly against 'unconfigured', and the disabled banner silently
  // didn't render. Send button stayed enabled. Treat unknown as
  // unconfigured so the safest default wins.
  const mode = isError ? 'unconfigured' : data?.mode;
  return { mode, isLoading, isError };
}

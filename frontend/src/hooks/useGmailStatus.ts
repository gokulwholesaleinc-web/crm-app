import { useQuery } from '@tanstack/react-query';
import { getGmailStatus, type GmailStatus } from '../api/integrations';

/**
 * Gmail connection status for the current user. Polled on a long
 * staleTime — Gmail tokens don't change frequently, but a sync failure
 * needs to be visible promptly.
 */
export function useGmailStatus() {
  return useQuery<GmailStatus>({
    queryKey: ['integrations', 'gmail', 'status'],
    queryFn: getGmailStatus,
    staleTime: 30_000,
  });
}

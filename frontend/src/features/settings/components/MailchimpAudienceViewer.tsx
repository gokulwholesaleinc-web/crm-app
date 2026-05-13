/**
 * Mailchimp audience viewer — paginated table that pulls the current
 * default audience's members from Mailchimp and cross-references each
 * row with CRM contacts/leads.
 *
 * Columns:
 *   • Email + name
 *   • Mailchimp status (subscribed/unsubscribed/cleaned/pending)
 *   • CRM match (link to contact, link to lead, or "drift" badge)
 *   • Last emailed timestamp (from the CRM's email queue)
 *
 * "Drift" rows are people in the Mailchimp audience but NOT in any CRM
 * contact/lead — after ops swaps to the empty CRM-Managed audience,
 * drift should be ~0. Anything higher is worth investigating.
 */

import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline';
import { Link } from 'react-router-dom';

import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import {
  type MailchimpAudienceMembersResponse,
  listMailchimpAudienceMembers,
} from '../../../api/integrations';
import { formatDate } from '../../../utils/formatters';

type StatusBadgeProps = { status: string };

function statusStyles(status: string): { bg: string; text: string } {
  switch (status) {
    case 'subscribed':
      return { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-400' };
    case 'unsubscribed':
      return { bg: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-700 dark:text-amber-400' };
    case 'cleaned':
      return { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-400' };
    case 'pending':
      return { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-400' };
    default:
      return { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-700 dark:text-gray-300' };
  }
}

function StatusBadge({ status }: StatusBadgeProps) {
  const s = statusStyles(status);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${s.bg} ${s.text}`}
    >
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

export function MailchimpAudienceViewer({ enabled }: { enabled: boolean }) {
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const { data, isLoading, isFetching, error } = useQuery<MailchimpAudienceMembersResponse>({
    queryKey: ['integrations', 'mailchimp', 'audience-members', page, pageSize],
    queryFn: () => listMailchimpAudienceMembers({ page, page_size: pageSize }),
    enabled,
  });

  // Reset to page 1 if the current page is beyond the last page of results.
  // This can happen when the viewer is closed at page N, audience shrinks,
  // and the viewer is reopened: Mailchimp returns items=[] but total>0.
  useEffect(() => {
    if (enabled && data && data.items.length === 0 && data.total > 0 && page > 1) {
      setPage(1);
    }
  }, [enabled, data, page]);

  if (!enabled) {
    return null;
  }

  if (isLoading) {
    return (
      <div className="mt-3 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
        <Spinner size="sm" /> Loading audience members&hellip;
      </div>
    );
  }

  if (error) {
    return (
      <p className="mt-3 rounded-md border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-2 text-xs text-red-700 dark:text-red-300">
        Could not load audience members. Check the Mailchimp connection.
      </p>
    );
  }

  if (!data || data.total === 0) {
    return (
      <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
        Audience is empty. Members will appear here as you send campaigns.
      </p>
    );
  }

  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
  const driftCount = data.items.filter((m) => m.drift).length;

  return (
    <div className="mt-3">
      <div className="mb-2 flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
        <span>
          Showing {data.items.length} of {data.total.toLocaleString()} audience members
        </span>
        {driftCount > 0 && (
          <span className="rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 px-2 py-0.5 text-amber-700 dark:text-amber-300">
            {driftCount} not in CRM on this page
          </span>
        )}
      </div>
      <div className="overflow-x-auto rounded-md border border-gray-200 dark:border-gray-700">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
          <thead className="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                Email
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                Status
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                CRM match
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase whitespace-nowrap">
                Last emailed
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800 bg-white dark:bg-gray-800">
            {data.items.map((m) => (
              <tr key={m.email}>
                <td className="px-3 py-2 align-top">
                  <div className="font-medium text-gray-900 dark:text-gray-100 break-all">
                    {m.email}
                  </div>
                  {m.full_name && (
                    <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                      {m.full_name}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2 align-top">
                  <StatusBadge status={m.mailchimp_status} />
                </td>
                <td className="px-3 py-2 align-top text-xs">
                  {m.crm_contact_id ? (
                    <Link
                      to={`/contacts/${m.crm_contact_id}`}
                      className="text-indigo-600 dark:text-indigo-400 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 rounded"
                    >
                      Contact #{m.crm_contact_id}
                    </Link>
                  ) : m.crm_lead_id ? (
                    <Link
                      to={`/leads/${m.crm_lead_id}`}
                      className="text-indigo-600 dark:text-indigo-400 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 rounded"
                    >
                      Lead #{m.crm_lead_id}
                    </Link>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 dark:bg-amber-900/20 px-2 py-0.5 text-amber-700 dark:text-amber-300 font-medium">
                      Drift
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 align-top text-xs text-gray-600 dark:text-gray-400 whitespace-nowrap">
                  {m.last_emailed_at ? formatDate(m.last_emailed_at, 'short') : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
        <span>
          Page {page} of {totalPages}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={page <= 1 || isFetching}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            leftIcon={<ChevronLeftIcon className="h-4 w-4" />}
          >
            Prev
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={page >= totalPages || isFetching}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            leftIcon={<ChevronRightIcon className="h-4 w-4" />}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}

export default MailchimpAudienceViewer;

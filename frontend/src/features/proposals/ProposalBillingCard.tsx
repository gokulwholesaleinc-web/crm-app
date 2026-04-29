import { CheckCircleIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import type { Proposal } from '../../types';
import { cadenceLabel, formatProposalMoneyOrDash } from './billing';

/**
 * Sidebar card on the proposal detail page that surfaces what the
 * client will actually be charged — payment type, amount + cadence,
 * and the Stripe artifact spawned on e-sign (invoice id, pay URL,
 * paid timestamp). Also shows `billing_error` when the Stripe spawn
 * failed so Giancarlo sees why there's no payment link yet.
 */

interface ProposalBillingCardProps {
  proposal: Proposal;
}

export function ProposalBillingCard({ proposal }: ProposalBillingCardProps) {
  const hasAmount = proposal.amount != null && proposal.amount !== '';
  const currency = proposal.currency ?? 'USD';
  const isSubscription = proposal.payment_type === 'subscription';

  const amountLine = formatProposalMoneyOrDash(proposal.amount, currency);
  const cadence = isSubscription
    ? cadenceLabel(proposal.recurring_interval, proposal.recurring_interval_count)
    : '';

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
      <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-4">Billing</h2>
      <dl className="space-y-3">
        <div>
          <dt className="text-xs text-gray-500 dark:text-gray-400">Type</dt>
          <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">
            {isSubscription ? 'Subscription' : 'One-time charge'}
          </dd>
        </div>

        <div>
          <dt className="text-xs text-gray-500 dark:text-gray-400">
            {isSubscription ? 'Per period' : 'Amount'}
          </dt>
          <dd className="text-sm font-semibold text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
            {amountLine}
            {isSubscription && cadence ? (
              <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">
                / {cadence.toLowerCase()}
              </span>
            ) : null}
          </dd>
          {!hasAmount && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              No amount set — client will not be auto-invoiced on acceptance.
            </p>
          )}
        </div>

        {proposal.paid_at && (
          <div className="pt-2 border-t border-gray-200 dark:border-gray-700">
            <dt className="text-xs text-gray-500 dark:text-gray-400">Status</dt>
            <dd className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-green-50 dark:bg-green-900/20 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:text-green-300">
              <CheckCircleIcon className="h-3.5 w-3.5" aria-hidden="true" />
              Paid · {formatDate(proposal.paid_at)}
            </dd>
          </div>
        )}

        {!proposal.paid_at && proposal.invoice_sent_at && (
          <div className="pt-2 border-t border-gray-200 dark:border-gray-700">
            <dt className="text-xs text-gray-500 dark:text-gray-400">Status</dt>
            <dd className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-indigo-50 dark:bg-indigo-900/20 px-2.5 py-0.5 text-xs font-medium text-indigo-700 dark:text-indigo-300">
              Awaiting payment · sent {formatDate(proposal.invoice_sent_at)}
            </dd>
          </div>
        )}

        {proposal.stripe_payment_url && !proposal.paid_at && (
          <div>
            <dt className="text-xs text-gray-500 dark:text-gray-400">Payment link</dt>
            <dd className="text-sm font-medium">
              <a
                href={proposal.stripe_payment_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300 break-all"
              >
                Open in Stripe
              </a>
            </dd>
          </div>
        )}

        {proposal.stripe_invoice_id && (
          <div>
            <dt className="text-xs text-gray-500 dark:text-gray-400">Stripe invoice</dt>
            <dd className="text-xs font-mono text-gray-700 dark:text-gray-300 break-all">
              {proposal.stripe_invoice_id}
            </dd>
          </div>
        )}

        {proposal.stripe_subscription_id && (
          <div>
            <dt className="text-xs text-gray-500 dark:text-gray-400">Stripe subscription</dt>
            <dd className="text-xs font-mono text-gray-700 dark:text-gray-300 break-all">
              {proposal.stripe_subscription_id}
            </dd>
          </div>
        )}

        {proposal.billing_error && (
          <div className="pt-2 border-t border-gray-200 dark:border-gray-700">
            <dt className="flex items-center gap-1.5 text-xs font-medium text-red-700 dark:text-red-400">
              <ExclamationTriangleIcon className="h-4 w-4" aria-hidden="true" />
              Billing setup failed
            </dt>
            <dd className="mt-1 text-xs text-red-600 dark:text-red-400 break-words">
              {proposal.billing_error}
            </dd>
            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              Fix the Stripe configuration, then retry from the API:
              <code className="ml-1 px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-900 text-gray-700 dark:text-gray-300">
                POST /api/proposals/{proposal.id}/retry-billing
              </code>
            </p>
          </div>
        )}
      </dl>
    </div>
  );
}

// Local formatDate import — extracted so this card is self-contained.
function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
  }).format(new Date(value));
}

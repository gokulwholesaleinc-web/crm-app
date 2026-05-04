/**
 * Payments tab body for contact and company detail pages.
 *
 * Lists every Stripe payment + subscription that flows through the
 * StripeCustomer linked to this CRM contact or company. The PaymentSummary
 * card on the Details tab shows the rollup numbers; this surface answers
 * "show me the actual line items."
 */

import { Link } from 'react-router-dom';
import { HelpLink, Spinner, StatusBadge } from '../ui';
import { usePayments, useSubscriptions } from '../../hooks/usePayments';
import { formatCurrency, formatDate } from '../../utils/formatters';
import { PaymentForLink } from '../../features/payments/PaymentsPage';
import type { Payment, SubscriptionItem } from '../../types';

type EntityType = 'contact' | 'company';

interface Props {
  entityType: EntityType;
  entityId: number;
}

function buildFilter(entityType: EntityType, entityId: number) {
  return entityType === 'contact'
    ? { contact_id: entityId, page_size: 50 }
    : { company_id: entityId, page_size: 50 };
}

export function EntityPaymentsTab({ entityType, entityId }: Props) {
  const filter = buildFilter(entityType, entityId);

  const { data: paymentsData, isLoading: paymentsLoading, error: paymentsError } =
    usePayments(filter);
  const { data: subsData, isLoading: subsLoading, error: subsError } =
    useSubscriptions(filter);

  const payments = paymentsData?.items ?? [];
  const subscriptions = subsData?.items ?? [];
  const hasNothing =
    !paymentsLoading && !subsLoading && payments.length === 0 && subscriptions.length === 0;

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 sm:px-6 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
            Payments
          </h3>
          <div className="flex items-center gap-3">
            <HelpLink anchor="tutorial-view-billings" label="How the Payments tab works" />
            <Link
              to="/payments"
              className="text-sm text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300"
            >
              Send invoice →
            </Link>
          </div>
        </div>
        {paymentsLoading ? (
          <div className="flex items-center justify-center py-8">
            <Spinner />
          </div>
        ) : paymentsError ? (
          <p className="px-4 py-6 text-sm text-red-500 dark:text-red-400">
            Failed to load payments.
          </p>
        ) : payments.length === 0 ? (
          <p className="px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
            No payments yet.
          </p>
        ) : (
          <PaymentsTable payments={payments} />
        )}
      </div>

      <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden">
        <div className="px-4 py-3 sm:px-6 border-b border-gray-200 dark:border-gray-700">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
            Subscriptions
          </h3>
        </div>
        {subsLoading ? (
          <div className="flex items-center justify-center py-8">
            <Spinner />
          </div>
        ) : subsError ? (
          <p className="px-4 py-6 text-sm text-red-500 dark:text-red-400">
            Failed to load subscriptions.
          </p>
        ) : subscriptions.length === 0 ? (
          <p className="px-4 py-6 text-sm text-gray-500 dark:text-gray-400">
            No active subscriptions.
          </p>
        ) : (
          <SubscriptionsTable subscriptions={subscriptions} />
        )}
      </div>

      {hasNothing && (
        <p className="text-xs text-gray-500 dark:text-gray-400 px-1">
          Tip: send an invoice from{' '}
          <Link to="/payments" className="text-primary-600 hover:underline">
            Payments
          </Link>
          {' '}or accept a Proposal to spawn billing automatically.
        </p>
      )}
    </div>
  );
}

function PaymentsTable({ payments }: { payments: Payment[] }) {
  return (
    <>
      {/* Mobile cards */}
      <div className="block md:hidden divide-y divide-gray-200 dark:divide-gray-700">
        {payments.map(payment => (
          <div key={payment.id} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700">
            <div className="flex items-start justify-between gap-2">
              <Link
                to={`/payments/${payment.id}`}
                className="text-sm font-medium text-primary-600 hover:text-primary-900 dark:hover:text-primary-300 truncate"
              >
                Payment #{payment.id}
              </Link>
              <StatusBadge status={payment.status} size="sm" showDot={false} />
            </div>
            <div className="mt-2 flex items-center justify-between text-sm">
              <span
                className="font-medium text-gray-900 dark:text-gray-100"
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {formatCurrency(payment.amount, payment.currency)}
              </span>
              <span className="text-gray-500 dark:text-gray-400">{formatDate(payment.created_at)}</span>
            </div>
            {(payment.proposal || payment.quote || payment.opportunity) && (
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 truncate">
                For <PaymentForLink payment={payment} />
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Desktop table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">ID</th>
              <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">For</th>
              <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
              <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Amount</th>
              <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Date</th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
            {payments.map(payment => (
              <tr key={payment.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  <Link
                    to={`/payments/${payment.id}`}
                    className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300"
                  >
                    #{payment.id}
                  </Link>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                  <PaymentForLink payment={payment} />
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <StatusBadge status={payment.status} size="sm" showDot={false} />
                </td>
                <td
                  className="px-6 py-4 whitespace-nowrap text-sm text-right font-medium text-gray-900 dark:text-gray-100"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  {formatCurrency(payment.amount, payment.currency)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                  {formatDate(payment.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function SubscriptionsTable({ subscriptions }: { subscriptions: SubscriptionItem[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead className="bg-gray-50 dark:bg-gray-900">
          <tr>
            <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">ID</th>
            <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
            <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Next Billing</th>
          </tr>
        </thead>
        <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
          {subscriptions.map(sub => (
            <tr key={sub.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-gray-100">
                #{sub.id}
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <StatusBadge status={sub.status} size="sm" showDot={false} />
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                {sub.current_period_end ? formatDate(sub.current_period_end) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default EntityPaymentsTab;

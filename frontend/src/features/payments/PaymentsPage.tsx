import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { StatusBadge, Button, EntityLink, HelpLink, PaginationBar } from '../../components/ui';
import { SkeletonTable } from '../../components/ui/Skeleton';
import { usePayments, useSubscriptions, useCancelSubscription } from '../../hooks/usePayments';
import { SendInvoiceModal } from './components/SendInvoiceModal';
import { formatCurrency, formatDate } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { showSuccess, showError } from '../../utils/toast';
import { StripeTestModeBanner } from '../../components/banners/StripeTestModeBanner';
import type { Payment, StripeCustomerBrief, SubscriptionItem } from '../../types';

function CustomerLink({
  customer,
  fallbackHref,
}: {
  customer: StripeCustomerBrief | null | undefined;
  fallbackHref?: string;
}) {
  const label = customer?.name ?? customer?.email ?? '-';
  if (customer?.contact_id) {
    return <EntityLink type="contact" id={customer.contact_id} variant="muted">{label}</EntityLink>;
  }
  if (customer?.company_id) {
    return <EntityLink type="company" id={customer.company_id} variant="muted">{label}</EntityLink>;
  }
  // No CRM target — keep the cell a tap target by linking to the surrounding fallback (e.g. payment detail).
  if (fallbackHref) {
    return (
      <Link to={fallbackHref} className="text-gray-600 hover:text-primary-700 dark:text-gray-400 dark:hover:text-primary-300">
        {label}
      </Link>
    );
  }
  return <>{label}</>;
}

// Renders the entity this payment is for: proposal > quote > opportunity.
// Returns a placeholder when the payment was created standalone.
export function PaymentForLink({ payment }: { payment: Payment }) {
  if (payment.proposal) {
    return (
      <EntityLink type="proposal" id={payment.proposal.id} variant="muted" title={payment.proposal.title}>
        Proposal {payment.proposal.proposal_number}
      </EntityLink>
    );
  }
  if (payment.quote) {
    return (
      <EntityLink type="quote" id={payment.quote.id} variant="muted" title={payment.quote.title}>
        Quote #{payment.quote.id}
      </EntityLink>
    );
  }
  if (payment.opportunity) {
    return (
      <EntityLink type="opportunity" id={payment.opportunity.id} variant="muted" title={payment.opportunity.name}>
        Opportunity #{payment.opportunity.id}
      </EntityLink>
    );
  }
  return <span className="text-gray-400 dark:text-gray-500">—</span>;
}

const TABS = ['All Payments', 'Subscriptions'] as const;
type Tab = (typeof TABS)[number];

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'succeeded', label: 'Succeeded' },
  { value: 'failed', label: 'Failed' },
  { value: 'refunded', label: 'Refunded' },
];

function PaymentsPage() {
  usePageTitle('Payments');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<Tab>('All Payments');
  const [showInvoiceModal, setShowInvoiceModal] = useState(false);
  const [statusFilter, setStatusFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState(searchParams.get('search') || '');
  const [currentPage, setCurrentPage] = useState(1);
  const [subPage, setSubPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const {
    data: paymentsData,
    isLoading,
    error,
  } = usePayments({
    page: currentPage,
    page_size: pageSize,
    status: statusFilter || undefined,
    search: searchQuery || undefined,
  });

  const {
    data: subscriptionsData,
    isLoading: subsLoading,
    error: subsError,
  } = useSubscriptions({ page: subPage, page_size: pageSize });

  const cancelMutation = useCancelSubscription();

  const payments = paymentsData?.items ?? [];
  const totalPages = paymentsData?.pages ?? 1;
  const total = paymentsData?.total ?? 0;

  const subscriptions = subscriptionsData?.items ?? [];
  const subTotalPages = subscriptionsData?.pages ?? 1;
  const subTotal = subscriptionsData?.total ?? 0;

  const handleCancel = async (sub: SubscriptionItem) => {
    try {
      await cancelMutation.mutateAsync(sub.id);
      showSuccess('Subscription canceled');
    } catch {
      showError('Failed to cancel subscription');
    }
  };

  const displayError = activeTab === 'All Payments' ? error : subsError;

  return (
    <div className="space-y-6">
      <StripeTestModeBanner />
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Payments</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Track and manage Stripe payments
          </p>
        </div>
        <div className="flex items-center gap-3">
          <HelpLink anchor="tutorial-create-invoice" label="How to send an invoice" text="How to send an invoice" />
          <Button variant="primary" onClick={() => setShowInvoiceModal(true)}>
            Send Invoice
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="-mb-px flex gap-6" aria-label="Payment tabs">
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => {
                setActiveTab(tab);
                setCurrentPage(1);
                setSubPage(1);
              }}
              className={`whitespace-nowrap border-b-2 py-3 px-1 text-sm font-medium transition-colors ${
                activeTab === tab
                  ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                  : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
            >
              {tab}
            </button>
          ))}
        </nav>
      </div>

      {/* Filters (only for All Payments) */}
      {activeTab === 'All Payments' && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 border border-transparent dark:border-gray-700">
          <div className="flex flex-col gap-3 sm:flex-row sm:gap-4 sm:items-center">
            <div className="flex-1 sm:flex-none sm:w-64">
              <label htmlFor="payment-search" className="sr-only">Search payments</label>
              <input
                id="payment-search"
                type="text"
                name="search"
                autoComplete="off"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                placeholder="Search by customer, amount, status..."
                className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 py-2.5 sm:py-2 text-base sm:text-sm"
              />
            </div>
            <div className="flex-1 sm:flex-none sm:w-48">
              <label htmlFor="payment-status-filter" className="sr-only">Filter by status</label>
              <select
                id="payment-status-filter"
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 py-2.5 sm:py-2 text-base sm:text-sm"
              >
                {statusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {displayError && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
          <p className="text-sm font-medium text-red-800 dark:text-red-300">
            {displayError instanceof Error ? displayError.message : 'An error occurred'}
          </p>
        </div>
      )}

      {/* All Payments Tab */}
      {activeTab === 'All Payments' && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
          {isLoading ? (
            <SkeletonTable rows={5} cols={5} />
          ) : payments.length === 0 ? (
            <div className="text-center py-12 px-4">
              <svg
                className="mx-auto h-12 w-12 text-gray-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No payments</h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                No payments have been recorded yet.
              </p>
            </div>
          ) : (
            <>
              {/* Mobile Card View */}
              <div className="block md:hidden divide-y divide-gray-200 dark:divide-gray-700">
                {payments.map((payment: Payment) => (
                  <div key={payment.id} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <Link
                          to={`/payments/${payment.id}`}
                          className="text-sm font-medium text-primary-600 hover:text-primary-900 dark:hover:text-primary-300 truncate block"
                        >
                          Payment #{payment.id}
                        </Link>
                        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                          <CustomerLink customer={payment.customer} fallbackHref={`/payments/${payment.id}`} />
                        </p>
                      </div>
                      <StatusBadge status={payment.status} size="sm" showDot={false} className="flex-shrink-0" />
                    </div>
                    <div className="mt-2 flex items-center justify-between text-sm">
                      <span className="font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {formatCurrency(payment.amount, payment.currency)}
                      </span>
                      <span className="text-gray-500 dark:text-gray-400">{formatDate(payment.created_at)}</span>
                    </div>
                    {(payment.proposal || payment.quote || payment.opportunity) && (
                      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 truncate">
                        For <PaymentForLink payment={payment} />
                      </p>
                    )}
                    {payment.payment_method && (
                      <p className="mt-1 text-xs text-gray-400 dark:text-gray-500 truncate">
                        {payment.payment_method}
                      </p>
                    )}
                  </div>
                ))}
              </div>

              {/* Desktop Table */}
              <div className="hidden md:block overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="bg-gray-50 dark:bg-gray-900">
                    <tr>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        ID
                      </th>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Customer
                      </th>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        For
                      </th>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Status
                      </th>
                      <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Amount
                      </th>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Date
                      </th>
                      <th scope="col" className="relative px-6 py-3">
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                    {payments.map((payment: Payment) => (
                      <tr
                        key={payment.id}
                        className="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
                        onClick={(e) => {
                          if ((e.target as HTMLElement).closest('a, button')) return;
                          navigate(`/payments/${payment.id}`);
                        }}
                      >
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-gray-100">
                          <Link
                            to={`/payments/${payment.id}`}
                            className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300"
                          >
                            #{payment.id}
                          </Link>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          <CustomerLink customer={payment.customer} />
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          <PaymentForLink payment={payment} />
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <StatusBadge status={payment.status} size="sm" showDot={false} />
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-right font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                          {formatCurrency(payment.amount, payment.currency)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          {formatDate(payment.created_at)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                          <Link
                            to={`/payments/${payment.id}`}
                            className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300"
                          >
                            View
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="bg-white dark:bg-gray-800 px-4 py-3 border-t border-gray-200 dark:border-gray-700 sm:px-6">
                <div className="flex items-center gap-4 mb-2 md:mb-0">
                  <select
                    value={pageSize}
                    onChange={(e) => {
                      setPageSize(Number(e.target.value));
                      setCurrentPage(1);
                    }}
                    aria-label="Results per page"
                    className="text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 px-2 py-1"
                  >
                    <option value={10}>10 / page</option>
                    <option value={25}>25 / page</option>
                    <option value={50}>50 / page</option>
                    <option value={100}>100 / page</option>
                  </select>
                </div>
                <PaginationBar
                  page={currentPage}
                  pages={totalPages}
                  total={total}
                  pageSize={pageSize}
                  onPageChange={setCurrentPage}
                />
              </div>
            </>
          )}
        </div>
      )}

      {/* Subscriptions Tab */}
      {activeTab === 'Subscriptions' && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
          {subsLoading ? (
            <SkeletonTable rows={5} cols={5} />
          ) : subscriptions.length === 0 ? (
            <div className="text-center py-12 px-4">
              <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No subscriptions</h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                No active subscriptions found.
              </p>
            </div>
          ) : (
            <>
              {/* Mobile Card View */}
              <div className="block md:hidden divide-y divide-gray-200 dark:divide-gray-700">
                {subscriptions.map((sub: SubscriptionItem) => (
                  <div key={sub.id} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                          {sub.customer?.name ?? sub.customer?.email ?? `Subscription #${sub.id}`}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                          {sub.stripe_subscription_id}
                        </p>
                      </div>
                      <StatusBadge status={sub.status} size="sm" showDot={false} className="flex-shrink-0" />
                    </div>
                    <div className="mt-2 flex items-center justify-between text-sm">
                      <span className="text-gray-500 dark:text-gray-400">
                        Next: {sub.current_period_end ? formatDate(sub.current_period_end) : '-'}
                      </span>
                      {sub.status === 'active' && !sub.cancel_at_period_end && (
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={() => handleCancel(sub)}
                          disabled={cancelMutation.isPending}
                        >
                          Cancel
                        </Button>
                      )}
                      {sub.cancel_at_period_end && (
                        <span className="text-xs text-orange-600 dark:text-orange-400">Cancels at period end</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Desktop Table */}
              <div className="hidden md:block overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="bg-gray-50 dark:bg-gray-900">
                    <tr>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Customer
                      </th>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Status
                      </th>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Current Period
                      </th>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Next Billing
                      </th>
                      <th scope="col" className="relative px-6 py-3">
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                    {subscriptions.map((sub: SubscriptionItem) => (
                      <tr key={sub.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-100">
                          {sub.customer?.name ?? sub.customer?.email ?? `#${sub.id}`}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <StatusBadge status={sub.status} size="sm" showDot={false} />
                          {sub.cancel_at_period_end && (
                            <span className="ml-2 text-xs text-orange-600 dark:text-orange-400">
                              Canceling
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          {sub.current_period_start ? formatDate(sub.current_period_start) : '-'}
                          {' - '}
                          {sub.current_period_end ? formatDate(sub.current_period_end) : '-'}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          {sub.current_period_end ? formatDate(sub.current_period_end) : '-'}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                          {sub.status === 'active' && !sub.cancel_at_period_end && (
                            <Button
                              variant="danger"
                              size="sm"
                              onClick={() => handleCancel(sub)}
                              disabled={cancelMutation.isPending}
                            >
                              {cancelMutation.isPending ? 'Canceling...' : 'Cancel'}
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <PaginationBar
                page={subPage}
                pages={subTotalPages}
                total={subTotal}
                pageSize={pageSize}
                onPageChange={setSubPage}
              />
            </>
          )}
        </div>
      )}

      <SendInvoiceModal
        isOpen={showInvoiceModal}
        onClose={() => setShowInvoiceModal(false)}
      />
    </div>
  );
}

export default PaymentsPage;

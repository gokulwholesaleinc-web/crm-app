import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeftIcon, DocumentArrowDownIcon, EnvelopeIcon, ClipboardDocumentIcon, ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline';
import { EntityLink, StatusBadge } from '../../components/ui';
import { usePayment } from '../../hooks/usePayments';
import { formatCurrency, formatDate } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { apiClient } from '../../api/client';
import { showSuccess, showError } from '../../utils/toast';
import type { StripeCustomerBrief } from '../../types';
import { StripeTestModeBanner } from '../../components/banners/StripeTestModeBanner';

function CustomerName({ customer }: { customer: StripeCustomerBrief }) {
  const label = customer.name ?? customer.email ?? customer.stripe_customer_id;
  if (customer.contact_id) {
    return <EntityLink type="contact" id={customer.contact_id}>{label}</EntityLink>;
  }
  if (customer.company_id) {
    return <EntityLink type="company" id={customer.company_id}>{label}</EntityLink>;
  }
  return <>{label}</>;
}

function PaymentDetailPage() {
  const { id } = useParams();
  const paymentId = id ? parseInt(id, 10) : undefined;

  const { data: payment, isLoading, error } = usePayment(paymentId);
  usePageTitle(payment ? `Payment #${payment.id}` : 'Payment');

  const [sendingReceipt, setSendingReceipt] = useState(false);
  const [receiptStatus, setReceiptStatus] = useState<string | null>(null);

  const handleDownloadInvoice = async () => {
    if (!payment) return;
    // window.open() can't carry the Authorization header so the new tab
    // would always 401 against the auth-protected endpoint. Fetch via
    // the apiClient (which injects the Bearer), turn the response into
    // a blob, and open it in a new tab via an object URL.
    try {
      const response = await apiClient.get(`/api/payments/${payment.id}/invoice`, {
        responseType: 'blob',
      });
      const blob = response.data as Blob;
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener,noreferrer');
      // Give the new tab a moment to attach to the URL before we revoke.
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      showError('Failed to load invoice. Try refreshing the page and signing in again.');
    }
  };

  const handleCopyPaymentUrl = async () => {
    if (!payment?.stripe_payment_url) return;
    try {
      await navigator.clipboard.writeText(payment.stripe_payment_url);
      showSuccess('Customer payment link copied to clipboard');
    } catch {
      showError('Failed to copy link');
    }
  };

  const handleResendReceipt = async () => {
    if (!payment) return;
    setSendingReceipt(true);
    setReceiptStatus(null);
    try {
      await apiClient.post(`/api/payments/${payment.id}/send-receipt`);
      setReceiptStatus('Receipt email sent successfully');
    } catch {
      setReceiptStatus('Failed to send receipt email');
    } finally {
      setSendingReceipt(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-1/3 mb-4" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2 mb-2" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/4" />
        </div>
      </div>
    );
  }

  if (error || !payment) {
    return (
      <div className="text-center py-12">
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Payment not found</h3>
        <Link to="/payments" className="mt-2 text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300">
          Back to Payments
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <Link
            to="/payments"
            className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
            aria-label="Back to payments"
          >
            <ArrowLeftIcon className="h-5 w-5" aria-hidden="true" />
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">
                Payment #{payment.id}
              </h1>
              <StatusBadge status={payment.status} size="sm" showDot={false} />
            </div>
            {payment.stripe_payment_intent_id && (
              <p className="text-sm text-gray-500 dark:text-gray-400">{payment.stripe_payment_intent_id}</p>
            )}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleDownloadInvoice}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
            aria-label="Download invoice"
          >
            <DocumentArrowDownIcon className="h-4 w-4" aria-hidden="true" />
            Download Invoice
          </button>
          <button
            type="button"
            onClick={handleResendReceipt}
            disabled={sendingReceipt}
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
            aria-label="Resend receipt email"
          >
            <EnvelopeIcon className="h-4 w-4" aria-hidden="true" />
            {sendingReceipt ? 'Sending...' : 'Resend Receipt'}
          </button>
        </div>
      </div>

      <StripeTestModeBanner />

      {/* Receipt status message */}
      {receiptStatus && (
        <div
          className={`rounded-lg p-3 text-sm ${
            receiptStatus.includes('success')
              ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800'
              : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800'
          }`}
          role="status"
          aria-live="polite"
        >
          {receiptStatus}
        </div>
      )}

      {payment.stripe_payment_url && payment.status !== 'succeeded' && (
        <div className="rounded-lg border border-primary-200 dark:border-primary-800 bg-primary-50 dark:bg-primary-900/10 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                Customer payment link
              </h3>
              <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
                Stripe emailed this to the customer when the invoice was sent. Use this if they
                say it never arrived (spam folder, wrong address, test mode).
              </p>
              <p className="mt-2 text-xs font-mono break-all text-gray-700 dark:text-gray-300">
                {payment.stripe_payment_url}
              </p>
            </div>
            <div className="flex gap-2 flex-shrink-0">
              <button
                type="button"
                onClick={handleCopyPaymentUrl}
                className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              >
                <ClipboardDocumentIcon className="h-4 w-4" aria-hidden="true" />
                Copy
              </button>
              <a
                href={payment.stripe_payment_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md border border-transparent bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              >
                <ArrowTopRightOnSquareIcon className="h-4 w-4" aria-hidden="true" />
                Preview
              </a>
            </div>
          </div>
        </div>
      )}

      {/* Payment Details Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Amount Card */}
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
            <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-4">Payment Amount</h2>
            <p className="text-3xl font-bold text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
              {formatCurrency(payment.amount, payment.currency)}
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Currency: {payment.currency}
            </p>
          </div>

          {/* Payment Method & Receipt */}
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
            <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-4">Payment Details</h2>
            <dl className="space-y-3">
              {payment.payment_method && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Payment Method</dt>
                  <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {payment.payment_method}
                  </dd>
                </div>
              )}
              {payment.receipt_url && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Receipt</dt>
                  <dd className="text-sm">
                    <a
                      href={payment.receipt_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary-600 hover:text-primary-900 dark:hover:text-primary-300"
                    >
                      View Receipt
                    </a>
                  </dd>
                </div>
              )}
              {payment.stripe_checkout_session_id && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Checkout Session</dt>
                  <dd className="text-sm text-gray-900 dark:text-gray-100 break-all">
                    {payment.stripe_checkout_session_id}
                  </dd>
                </div>
              )}
            </dl>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Info */}
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
            <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-4">Details</h2>
            <dl className="space-y-3">
              <div>
                <dt className="text-xs text-gray-500 dark:text-gray-400">Created</dt>
                <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(payment.created_at)}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500 dark:text-gray-400">Updated</dt>
                <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(payment.updated_at)}</dd>
              </div>
            </dl>
          </div>

          {/* Related Entities */}
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
            <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-4">Related</h2>
            <dl className="space-y-3">
              {payment.customer && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Customer</dt>
                  <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    <CustomerName customer={payment.customer} />
                  </dd>
                </div>
              )}
              {payment.proposal && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Proposal</dt>
                  <dd className="text-sm font-medium">
                    <EntityLink type="proposal" id={payment.proposal.id}>
                      {payment.proposal.title} ({payment.proposal.proposal_number})
                    </EntityLink>
                  </dd>
                </div>
              )}
              {payment.opportunity && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Opportunity</dt>
                  <dd className="text-sm font-medium">
                    <EntityLink type="opportunity" id={payment.opportunity.id}>
                      {payment.opportunity.name}
                    </EntityLink>
                  </dd>
                </div>
              )}
              {payment.quote && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Quote</dt>
                  <dd className="text-sm font-medium">
                    <EntityLink type="quote" id={payment.quote.id}>
                      {payment.quote.title}
                    </EntityLink>
                  </dd>
                </div>
              )}
              {!payment.customer && !payment.opportunity && !payment.quote && !payment.proposal && (
                <p className="text-sm text-gray-500 dark:text-gray-400">No related entities</p>
              )}
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PaymentDetailPage;

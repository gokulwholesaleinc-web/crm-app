import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { apiClient } from '../../api/client';

interface QuoteBranding {
  company_name: string | null;
  logo_url: string | null;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  footer_text: string | null;
}

interface QuoteLineItem {
  description: string;
  quantity: number;
  unit_price: number;
  discount: number;
  total: number;
}

interface PublicQuote {
  quote_number: string;
  title: string;
  description: string | null;
  status: string;
  currency: string;
  valid_until: string | null;
  subtotal: number;
  tax_amount: number;
  total: number;
  discount_type: string | null;
  discount_value: number;
  terms_and_conditions: string | null;
  payment_type: string;
  recurring_interval: string | null;
  line_items: QuoteLineItem[];
  company: { id: number; name: string } | null;
  contact: { id: number; full_name: string } | null;
  branding: QuoteBranding | null;
}

const DEFAULT_BRANDING: QuoteBranding = {
  company_name: null,
  logo_url: null,
  primary_color: '#6366f1',
  secondary_color: '#8b5cf6',
  accent_color: '#22c55e',
  footer_text: null,
};

function formatCurrency(value: number, currency: string): string {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatDate(dateStr: string): string {
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(new Date(dateStr));
}

function PublicQuoteView() {
  const { quoteNumber } = useParams<{ quoteNumber: string }>();
  const [quote, setQuote] = useState<PublicQuote | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [actionDone, setActionDone] = useState<'accepted' | 'rejected' | null>(null);

  // E-sign modal state
  const [showEsignModal, setShowEsignModal] = useState(false);
  const [signerName, setSignerName] = useState('');
  const [signerEmail, setSignerEmail] = useState('');
  const [esignError, setEsignError] = useState<string | null>(null);

  useEffect(() => {
    if (!quoteNumber) return;

    const fetchQuote = async () => {
      try {
        const response = await apiClient.get<PublicQuote>(
          `/api/quotes/public/${quoteNumber}`
        );
        setQuote(response.data);
      } catch {
        setError('Quote not found or no longer available.');
      } finally {
        setLoading(false);
      }
    };

    fetchQuote();
  }, [quoteNumber]);

  const handleAcceptClick = useCallback(() => {
    setEsignError(null);
    setShowEsignModal(true);
  }, []);

  const handleEsignSubmit = useCallback(async () => {
    if (!signerName.trim() || !signerEmail.trim()) {
      setEsignError('Please provide both your name and email address.');
      return;
    }

    setActionPending(true);
    setEsignError(null);
    try {
      const response = await apiClient.post<PublicQuote>(
        `/api/quotes/public/${quoteNumber}/accept`,
        { signer_name: signerName.trim(), signer_email: signerEmail.trim() }
      );
      setQuote(response.data);
      setActionDone('accepted');
      setShowEsignModal(false);
    } catch {
      setEsignError('Failed to accept the quote. Please try again.');
    } finally {
      setActionPending(false);
    }
  }, [quoteNumber, signerName, signerEmail]);

  const handleReject = useCallback(async () => {
    if (!quote) return;
    setActionPending(true);
    try {
      const response = await apiClient.post<PublicQuote>(
        `/api/quotes/public/${quoteNumber}/reject`,
        {}
      );
      setQuote(response.data);
      setActionDone('rejected');
    } catch {
      setActionDone('rejected');
    } finally {
      setActionPending(false);
    }
  }, [quote, quoteNumber]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="animate-pulse text-center">
          <div className="h-8 w-48 bg-gray-200 dark:bg-gray-700 rounded mx-auto mb-4" />
          <div className="h-4 w-32 bg-gray-200 dark:bg-gray-700 rounded mx-auto" />
        </div>
      </div>
    );
  }

  if (error || !quote) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center px-4">
        <div className="text-center max-w-md">
          <svg
            className="mx-auto h-16 w-16 text-gray-400 dark:text-gray-500 mb-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
            />
          </svg>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Quote Not Found
          </h1>
          <p className="text-gray-500 dark:text-gray-400">
            {error || 'This quote may have been removed or the link is invalid.'}
          </p>
        </div>
      </div>
    );
  }

  const branding = quote.branding ?? DEFAULT_BRANDING;
  const companyDisplayName = branding.company_name || quote.company?.name || 'Quote';

  const isExpired =
    quote.valid_until &&
    new Date(quote.valid_until) < new Date();

  const canRespond =
    (quote.status === 'sent' || quote.status === 'viewed') &&
    !isExpired &&
    !actionDone;

  const formattedValidUntil = quote.valid_until
    ? formatDate(quote.valid_until)
    : null;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Branded Top Bar */}
      <header
        className="sticky top-0 z-10 border-b border-gray-200 dark:border-gray-700"
        style={{ backgroundColor: branding.primary_color }}
      >
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            {branding.logo_url ? (
              <img
                src={branding.logo_url}
                alt={companyDisplayName}
                width={36}
                height={36}
                className="rounded"
                style={{ maxHeight: 36 }}
              />
            ) : null}
            <span className="text-lg font-semibold text-white truncate">
              {companyDisplayName}
            </span>
          </div>
          <div className="flex items-center gap-2 text-sm text-white/80">
            <span>{quote.quote_number}</span>
            {quote.status === 'accepted' || actionDone === 'accepted' ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                <CheckIcon className="h-3 w-3" aria-hidden="true" />
                Accepted
              </span>
            ) : quote.status === 'rejected' || actionDone === 'rejected' ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                <XMarkIcon className="h-3 w-3" aria-hidden="true" />
                Rejected
              </span>
            ) : null}
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Title & Valid Until */}
        <div>
          <h1
            className="text-2xl sm:text-3xl font-bold"
            style={{ color: branding.primary_color, textWrap: 'balance' }}
          >
            {quote.title}
          </h1>
          {quote.contact && (
            <p className="mt-1 text-gray-500 dark:text-gray-400">
              Prepared for {quote.contact.full_name}
            </p>
          )}
          {quote.description && (
            <p className="mt-2 text-gray-600 dark:text-gray-300">
              {quote.description}
            </p>
          )}
          {formattedValidUntil && (
            <p className={`mt-2 text-sm ${isExpired ? 'text-red-600 dark:text-red-400 font-medium' : 'text-gray-500 dark:text-gray-400'}`}>
              {isExpired ? 'Expired on ' : 'Valid until '}{formattedValidUntil}
            </p>
          )}
          {quote.payment_type === 'subscription' && quote.recurring_interval && (
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Recurring: {quote.recurring_interval}
            </p>
          )}
        </div>

        {/* Line Items Table */}
        {quote.line_items.length > 0 && (
          <section
            className="rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden"
            style={{ backgroundColor: `${branding.secondary_color}10` }}
          >
            <div className="px-6 sm:px-8 pt-6 sm:pt-8 pb-4">
              <h2
                className="text-lg font-semibold mb-4"
                style={{ color: branding.primary_color }}
              >
                Line Items
              </h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-t border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
                    <th className="px-6 sm:px-8 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">
                      Description
                    </th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-600 dark:text-gray-300" style={{ fontVariantNumeric: 'tabular-nums' }}>
                      Qty
                    </th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-600 dark:text-gray-300" style={{ fontVariantNumeric: 'tabular-nums' }}>
                      Unit Price
                    </th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-600 dark:text-gray-300" style={{ fontVariantNumeric: 'tabular-nums' }}>
                      Discount
                    </th>
                    <th className="px-6 sm:px-8 py-3 text-right font-semibold text-gray-600 dark:text-gray-300" style={{ fontVariantNumeric: 'tabular-nums' }}>
                      Total
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {quote.line_items.map((item, index) => (
                    <tr
                      key={index}
                      className="border-b border-gray-200 dark:border-gray-700 last:border-b-0"
                    >
                      <td className="px-6 sm:px-8 py-3 text-gray-900 dark:text-gray-100 break-words">
                        {item.description}
                      </td>
                      <td className="px-4 py-3 text-right text-gray-700 dark:text-gray-300" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {new Intl.NumberFormat(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(item.quantity)}
                      </td>
                      <td className="px-4 py-3 text-right text-gray-700 dark:text-gray-300" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {formatCurrency(item.unit_price, quote.currency)}
                      </td>
                      <td className="px-4 py-3 text-right text-gray-700 dark:text-gray-300" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {item.discount > 0 ? formatCurrency(item.discount, quote.currency) : '\u2014'}
                      </td>
                      <td className="px-6 sm:px-8 py-3 text-right font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {formatCurrency(item.total, quote.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* Totals Summary */}
        <section className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 sm:p-8">
          <h2
            className="text-lg font-semibold mb-4"
            style={{ color: branding.primary_color }}
          >
            Summary
          </h2>
          <dl className="space-y-2 text-sm" style={{ fontVariantNumeric: 'tabular-nums' }}>
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">Subtotal</dt>
              <dd className="text-gray-900 dark:text-gray-100 font-medium">
                {formatCurrency(quote.subtotal, quote.currency)}
              </dd>
            </div>
            {quote.discount_value > 0 && (
              <div className="flex justify-between">
                <dt className="text-gray-500 dark:text-gray-400">
                  Discount{quote.discount_type === 'percent' ? ` (${quote.discount_value}%)` : ''}
                </dt>
                <dd className="text-red-600 dark:text-red-400 font-medium">
                  {quote.discount_type === 'percent'
                    ? `-${formatCurrency(quote.subtotal * (quote.discount_value / 100), quote.currency)}`
                    : `-${formatCurrency(quote.discount_value, quote.currency)}`}
                </dd>
              </div>
            )}
            {quote.tax_amount > 0 && (
              <div className="flex justify-between">
                <dt className="text-gray-500 dark:text-gray-400">Tax</dt>
                <dd className="text-gray-900 dark:text-gray-100 font-medium">
                  {formatCurrency(quote.tax_amount, quote.currency)}
                </dd>
              </div>
            )}
            <div className="flex justify-between border-t border-gray-200 dark:border-gray-700 pt-3 mt-3">
              <dt className="text-base font-semibold text-gray-900 dark:text-gray-100">Total</dt>
              <dd
                className="text-base font-bold"
                style={{ color: branding.primary_color }}
              >
                {formatCurrency(quote.total, quote.currency)}
              </dd>
            </div>
          </dl>
        </section>

        {/* Terms and Conditions */}
        {quote.terms_and_conditions && (
          <section
            className="rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 sm:p-8"
            style={{ backgroundColor: `${branding.secondary_color}10` }}
          >
            <h2
              className="text-lg font-semibold mb-4"
              style={{ color: branding.primary_color }}
            >
              Terms and Conditions
            </h2>
            <p className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed break-words">
              {quote.terms_and_conditions}
            </p>
          </section>
        )}

        {/* Accept / Reject Actions */}
        {canRespond && (
          <section className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 sm:p-8">
            <h2
              className="text-lg font-semibold mb-2"
              style={{ color: branding.primary_color }}
            >
              Your Response
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
              Please review the quote above and accept or reject it.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                type="button"
                aria-label="Accept this quote"
                onClick={handleAcceptClick}
                disabled={actionPending}
                className="inline-flex items-center justify-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50"
                style={{ backgroundColor: branding.accent_color, outlineColor: branding.accent_color }}
              >
                <CheckIcon className="h-5 w-5" aria-hidden="true" />
                Accept Quote
              </button>
              <button
                type="button"
                aria-label="Reject this quote"
                onClick={handleReject}
                disabled={actionPending}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-white dark:bg-gray-700 px-6 py-3 text-sm font-semibold text-gray-900 dark:text-gray-100 shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-500 disabled:opacity-50"
              >
                <XMarkIcon className="h-5 w-5" aria-hidden="true" />
                Reject Quote
              </button>
            </div>
          </section>
        )}

        {/* Action Confirmation */}
        {actionDone && (
          <section
            className={`rounded-lg p-6 sm:p-8 ${
              actionDone === 'accepted'
                ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
            }`}
          >
            <div className="flex items-center gap-3">
              {actionDone === 'accepted' ? (
                <CheckIcon className="h-6 w-6 text-green-600 dark:text-green-400" aria-hidden="true" />
              ) : (
                <XMarkIcon className="h-6 w-6 text-red-600 dark:text-red-400" aria-hidden="true" />
              )}
              <div>
                <h3
                  className={`font-semibold ${
                    actionDone === 'accepted' ? 'text-green-800 dark:text-green-300' : 'text-red-800 dark:text-red-300'
                  }`}
                >
                  {actionDone === 'accepted'
                    ? 'Quote Accepted'
                    : 'Quote Rejected'}
                </h3>
                <p
                  className={`text-sm mt-1 ${
                    actionDone === 'accepted' ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'
                  }`}
                >
                  {actionDone === 'accepted'
                    ? 'Thank you for accepting this quote. We will be in touch shortly.'
                    : 'Thank you for your response. We appreciate your time.'}
                </p>
              </div>
            </div>
          </section>
        )}
      </main>

      {/* Branded Footer */}
      <footer className="border-t border-gray-200 dark:border-gray-700 mt-12">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6 text-center text-sm text-gray-400 dark:text-gray-500">
          {branding.footer_text ? (
            <p className="mb-1">{branding.footer_text}</p>
          ) : null}
          <p>
            {companyDisplayName} &middot; {quote.quote_number}
          </p>
        </div>
      </footer>

      {/* E-Sign Modal */}
      {showEsignModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="esign-modal-title"
        >
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl max-w-md w-full p-6 sm:p-8">
            <h2
              id="esign-modal-title"
              className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1"
            >
              Confirm Acceptance
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
              By providing your name and email, you agree to accept this quote as a binding agreement.
            </p>

            {esignError && (
              <div className="mb-4 rounded-md bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-700 dark:text-red-300">
                {esignError}
              </div>
            )}

            <div className="space-y-4">
              <div>
                <label
                  htmlFor="signer-name"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Full Name
                </label>
                <input
                  id="signer-name"
                  type="text"
                  name="signer_name"
                  autoComplete="name"
                  value={signerName}
                  onChange={(e) => setSignerName(e.target.value)}
                  placeholder="Jane Smith..."
                  className="block w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-0"
                  style={{ outlineColor: branding.primary_color }}
                />
              </div>
              <div>
                <label
                  htmlFor="signer-email"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Email Address
                </label>
                <input
                  id="signer-email"
                  type="email"
                  name="signer_email"
                  autoComplete="email"
                  inputMode="email"
                  spellCheck={false}
                  value={signerEmail}
                  onChange={(e) => setSignerEmail(e.target.value)}
                  placeholder="jane@company.com..."
                  className="block w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-0"
                  style={{ outlineColor: branding.primary_color }}
                />
              </div>
            </div>

            <div className="flex flex-col-reverse sm:flex-row gap-3 mt-6">
              <button
                type="button"
                aria-label="Cancel acceptance"
                onClick={() => setShowEsignModal(false)}
                disabled={actionPending}
                className="flex-1 rounded-lg bg-white dark:bg-gray-700 px-4 py-2.5 text-sm font-semibold text-gray-900 dark:text-gray-100 shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-500 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                aria-label="Confirm and sign acceptance"
                onClick={handleEsignSubmit}
                disabled={actionPending}
                className="flex-1 rounded-lg px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50"
                style={{ backgroundColor: branding.accent_color, outlineColor: branding.accent_color }}
              >
                {actionPending ? 'Signing...' : 'Accept & Sign'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default PublicQuoteView;

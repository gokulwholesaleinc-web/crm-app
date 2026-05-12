import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import axios from 'axios';
import { sanitizeHexColor } from '../../utils/colorValidation';
import { useForceLightMode } from '../../hooks/useForceLightMode';
import { formatCurrency, formatDate } from '../../utils/formatters';
import { setPublicPageMeta } from './publicMeta';
import { Modal, ModalFooter } from '../../components/ui/Modal';

// Bare axios for public (unauthenticated) quote endpoints. Does NOT
// attach CRM Bearer token or X-Tenant-Slug header so a CRM staff user
// previewing their own public link doesn't leak credentials or get
// logged out on a 401. See audit Session 2 report.
const publicClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

interface QuoteBranding {
  company_name: string | null;
  logo_url: string | null;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  bg_color_light: string;
  surface_color_light: string;
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
  bg_color_light: '#f9fafb',
  surface_color_light: '#ffffff',
  footer_text: null,
};

function PublicQuoteView() {
  // URL parameter is now the unguessable Quote.public_token, not the
  // sequential quote_number. The React Router path still uses the
  // :quoteNumber name for backwards compatibility — we just treat its
  // value as an opaque token.
  const { quoteNumber: token } = useParams<{ quoteNumber: string }>();
  const [quote, setQuote] = useState<PublicQuote | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [actionDone, setActionDone] = useState<'accepted' | 'rejected' | null>(null);

  // E-sign modal state
  const [logoError, setLogoError] = useState(false);
  const [showEsignModal, setShowEsignModal] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectEmail, setRejectEmail] = useState('');
  const [rejectError, setRejectError] = useState<string | null>(null);
  const [signerName, setSignerName] = useState('');
  const [signerEmail, setSignerEmail] = useState('');
  const [esignError, setEsignError] = useState<string | null>(null);
  const [esignChecked, setEsignChecked] = useState(false);

  useForceLightMode();

  useEffect(() => {
    setLogoError(false);
  }, [quote?.branding?.logo_url]);

  const quoteNumber = quote?.quote_number;
  const quoteBrandingCompanyName = quote?.branding?.company_name;
  useEffect(() => {
    if (!quoteNumber) return;
    const company = quoteBrandingCompanyName ?? 'Quote';
    const title = `Quote ${quoteNumber} — ${company}`;
    const previous = document.title;
    document.title = title;
    const restoreMeta = setPublicPageMeta({
      title,
      description: `Quote ${quoteNumber} from ${company}.`,
      type: 'article',
      canonicalUrl: window.location.href,
    });
    return () => {
      document.title = previous;
      restoreMeta();
    };
  }, [quoteNumber, quoteBrandingCompanyName]);

  useEffect(() => {
    if (!token) return;

    const fetchQuote = async () => {
      try {
        const response = await publicClient.get<PublicQuote>(
          `/api/quotes/public/${token}`
        );
        setQuote(response.data);
      } catch {
        setError('Quote not found or no longer available.');
      } finally {
        setLoading(false);
      }
    };

    fetchQuote();
  }, [token]);

  const handleAcceptClick = useCallback(() => {
    setEsignError(null);
    setEsignChecked(false);
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
      const response = await publicClient.post<PublicQuote>(
        `/api/quotes/public/${token}/accept`,
        { signer_name: signerName.trim(), signer_email: signerEmail.trim() }
      );
      setQuote(response.data);
      setActionDone('accepted');
      setShowEsignModal(false);
    } catch (err) {
      // Surface server error if available — the backend returns
      // "Signer email does not match the quote recipient" when the
      // customer types an email that doesn't match their own contact.
      const detail =
        (typeof err === 'object' && err !== null && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null) || 'Failed to accept the quote. Please try again.';
      setEsignError(detail);
    } finally {
      setActionPending(false);
    }
  }, [token, signerName, signerEmail]);

  const handleRejectClick = useCallback(() => {
    setRejectError(null);
    setShowRejectModal(true);
  }, []);

  const handleRejectSubmit = useCallback(async () => {
    if (!quote) return;
    const email = rejectEmail.trim();
    if (!email) {
      setRejectError('Please enter your email address to reject this quote.');
      return;
    }
    setActionPending(true);
    setRejectError(null);
    try {
      const response = await publicClient.post<PublicQuote>(
        `/api/quotes/public/${token}/reject`,
        { signer_email: email },
      );
      setQuote(response.data);
      setActionDone('rejected');
      setShowRejectModal(false);
    } catch (err) {
      const detail =
        (typeof err === 'object' && err !== null && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null) || 'Unable to record rejection. Please contact your account manager.';
      setRejectError(detail);
    } finally {
      setActionPending(false);
    }
  }, [quote, token, rejectEmail]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div role="status" aria-label="Loading quote…" className="animate-pulse motion-reduce:animate-none text-center">
          <div className="h-8 w-48 bg-gray-200 rounded mx-auto mb-4" />
          <div className="h-4 w-32 bg-gray-200 rounded mx-auto" />
        </div>
      </div>
    );
  }

  if (error || !quote) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="text-center max-w-md">
          <h1 className="text-xl font-semibold text-gray-900 mb-2">Quote not found</h1>
          <p className="text-gray-500">{error || 'This quote may have been removed or the link is no longer valid. Please contact your account manager.'}</p>
        </div>
      </div>
    );
  }

  const rawBranding = quote.branding ?? DEFAULT_BRANDING;
  // Tenant branding colors come from the server as arbitrary strings. Strip
  // any value that isn't a strict hex color before it hits an inline
  // `style={{ backgroundColor: ... }}` — a malformed color otherwise gets
  // echoed into the DOM verbatim.
  const branding = {
    ...rawBranding,
    primary_color: sanitizeHexColor(rawBranding.primary_color, DEFAULT_BRANDING.primary_color),
    secondary_color: sanitizeHexColor(rawBranding.secondary_color, DEFAULT_BRANDING.secondary_color),
    accent_color: sanitizeHexColor(rawBranding.accent_color, DEFAULT_BRANDING.accent_color),
    bg_color_light: sanitizeHexColor(rawBranding.bg_color_light, DEFAULT_BRANDING.bg_color_light),
    surface_color_light: sanitizeHexColor(rawBranding.surface_color_light, DEFAULT_BRANDING.surface_color_light),
  };
  const companyDisplayName = branding.company_name || quote.company?.name || 'Quote';

  const isExpired =
    quote.valid_until &&
    new Date(quote.valid_until) < new Date();

  const canRespond =
    (quote.status === 'sent' || quote.status === 'viewed') &&
    !isExpired &&
    !actionDone;

  const formattedValidUntil = quote.valid_until
    ? formatDate(quote.valid_until, 'long')
    : null;

  const primary = branding.primary_color;
  const accent = branding.accent_color;

  return (
    <div className="min-h-screen text-gray-900 antialiased" style={{ backgroundColor: branding.bg_color_light }}>
      <div
        aria-hidden="true"
        style={{
          height: 4,
          backgroundImage: `linear-gradient(90deg, ${primary}, ${branding.secondary_color}, ${accent})`,
        }}
      />
      <header className="border-b border-gray-200" style={{ backgroundColor: branding.surface_color_light }}>
        <div className="mx-auto max-w-3xl px-6 sm:px-10 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            {branding.logo_url && !logoError ? (
              <img
                src={branding.logo_url}
                alt={companyDisplayName}
                width={180}
                height={30}
                className="object-contain"
                style={{ height: 30, width: 'auto', maxWidth: 180 }}
                onError={() => setLogoError(true)}
              />
            ) : (
              <>
                <div
                  className="h-8 w-8 rounded flex items-center justify-center flex-shrink-0 text-white text-sm font-semibold"
                  style={{ backgroundColor: primary }}
                >
                  {companyDisplayName[0]?.toUpperCase() || 'Q'}
                </div>
                <span className="text-[15px] font-semibold text-gray-900 truncate">
                  {companyDisplayName}
                </span>
              </>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className="tabular-nums">{quote.quote_number}</span>
            {(quote.status === 'accepted' || actionDone === 'accepted') && (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium text-white"
                style={{ backgroundColor: accent }}
              >
                <CheckIcon className="h-3 w-3" aria-hidden="true" />
                Accepted
              </span>
            )}
            {(quote.status === 'rejected' || actionDone === 'rejected') && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
                <XMarkIcon className="h-3 w-3" aria-hidden="true" />
                Rejected
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 sm:px-10 py-10 sm:py-14 space-y-10 sm:space-y-12">
        {/* Cover — matches Proposal/Contract letterhead style */}
        <section className="pb-8 border-b border-gray-200">
          <p className="text-xs uppercase tracking-wider text-gray-500 mb-3">
            Quote <span className="text-gray-300 mx-1">·</span>
            <span className="tabular-nums">{quote.quote_number}</span>
          </p>
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 leading-tight tracking-tight text-balance">
            {quote.title}
          </h1>
          {quote.contact && (
            <p className="mt-3 text-[15px] text-gray-600">
              Prepared for <span className="font-medium text-gray-900">{quote.contact.full_name}</span>
              {quote.company?.name && (
                <span className="text-gray-500"> · {quote.company.name}</span>
              )}
            </p>
          )}
          {quote.description && (
            <p className="mt-2 text-[15px] text-gray-600 leading-relaxed">
              {quote.description}
            </p>
          )}
          {formattedValidUntil && (
            <p className={`mt-2 text-sm ${isExpired ? 'text-red-600 font-medium' : 'text-gray-500'}`}>
              {isExpired ? 'Expired on ' : 'Valid until '}<span className="tabular-nums">{formattedValidUntil}</span>
            </p>
          )}
          {quote.payment_type === 'subscription' && quote.recurring_interval && (
            <p className="mt-1 text-sm text-gray-500">
              Recurring: {quote.recurring_interval}
            </p>
          )}
        </section>

        {/* Expired banner — matches Contract pattern */}
        {isExpired && (
          <section className="rounded-lg shadow-sm border border-amber-200 bg-amber-50 px-5 py-4" role="status">
            <p className="text-sm font-medium text-amber-900">
              This quote has expired. Please contact your account manager for a new link.
            </p>
          </section>
        )}

        {/* Line Items Table */}
        {quote.line_items.length > 0 && (
          <section
            className="rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden"
            style={{ backgroundColor: `${branding.secondary_color}10` }}
          >
            <div className="px-6 sm:px-8 pt-6 sm:pt-8 pb-4">
              <h2 className="text-lg font-semibold mb-4 text-gray-900">
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
        <section className="rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8" style={{ backgroundColor: branding.surface_color_light }}>
          <h2 className="text-lg font-semibold mb-4 text-gray-900">
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
            <h2 className="text-lg font-semibold mb-4 text-gray-900">
              Terms and Conditions
            </h2>
            <p className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed break-words">
              {quote.terms_and_conditions}
            </p>
          </section>
        )}

        {/* Accept / Reject Actions */}
        {canRespond && (
          <section className="rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8" style={{ backgroundColor: branding.surface_color_light }}>
            <h2 className="text-lg font-semibold mb-2 text-gray-900">
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
                onClick={handleRejectClick}
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
        {actionDone && (() => {
          const accepted = actionDone === 'accepted';
          const tone = accepted
            ? {
                section: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
                heading: 'text-green-800 dark:text-green-300',
                body: 'text-green-700 dark:text-green-400',
                title: 'Quote Accepted',
                message: 'A signed copy will be emailed to the address you provided. You can safely close this page.',
              }
            : {
                section: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
                heading: 'text-red-800 dark:text-red-300',
                body: 'text-red-700 dark:text-red-400',
                title: 'Quote Rejected',
                message: 'Thank you for your response. We appreciate your time.',
              };

          return (
            <section
              role="status"
              aria-live="polite"
              className={`rounded-lg p-6 sm:p-8 border ${tone.section}`}
            >
              <div className="flex items-center gap-3">
                {accepted ? (
                  <CheckIcon className="h-6 w-6 text-green-600 dark:text-green-400" aria-hidden="true" />
                ) : (
                  <XMarkIcon className="h-6 w-6 text-red-600 dark:text-red-400" aria-hidden="true" />
                )}
                <div>
                  <h3 className={`font-semibold ${tone.heading}`}>{tone.title}</h3>
                  <p className={`text-sm mt-1 ${tone.body}`}>{tone.message}</p>
                </div>
              </div>
            </section>
          );
        })()}
      </main>

      {/* Branded Footer — pads with safe-area-inset-bottom so iPhone home
          indicator doesn't overlap the footer text. Requires viewport-fit=cover
          on the <meta name=viewport> tag (set in index.html). */}
      <footer
        className="mt-16 border-t border-gray-200"
        style={{ backgroundColor: branding.surface_color_light, paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <div className="mx-auto max-w-3xl px-6 sm:px-10 py-8 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-gray-900">{companyDisplayName}</p>
              {branding.footer_text && (
                <p className="text-xs text-gray-500 leading-relaxed max-w-sm">{branding.footer_text}</p>
              )}
              <p className="text-xs text-gray-400 tabular-nums mt-1">{quote.quote_number}</p>
            </div>
          </div>
        </div>
      </footer>

      {/* E-Sign Modal */}
      <Modal
        isOpen={showEsignModal}
        onClose={() => { setShowEsignModal(false); setEsignChecked(false); }}
        title="Confirm Acceptance"
        description="By providing your name and email, you agree to accept this quote as a binding agreement."
        size="md"
        closeOnOverlayClick={!actionPending}
      >
        {esignError && (
          <div
            role="alert"
            aria-live="polite"
            className="mb-4 rounded-md bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-700 dark:text-red-300"
          >
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

        <div className="mt-4 flex items-start gap-2.5">
          <input
            type="checkbox"
            id="esign-agree"
            checked={esignChecked}
            onChange={(e) => setEsignChecked(e.target.checked)}
            disabled={actionPending}
            className="mt-0.5 h-4 w-4 rounded border-gray-300 focus-visible:outline focus-visible:outline-2"
            style={{ accentColor: branding.primary_color }}
          />
          <label htmlFor="esign-agree" className="text-sm text-gray-700 dark:text-gray-300 leading-snug cursor-pointer">
            I have read and agree to the terms and conditions above
          </label>
        </div>

        <ModalFooter>
          <button
            type="button"
            aria-label="Cancel acceptance"
            onClick={() => { setShowEsignModal(false); setEsignChecked(false); }}
            disabled={actionPending}
            className="flex-1 rounded-lg bg-white dark:bg-gray-700 px-4 py-2.5 text-sm font-semibold text-gray-900 dark:text-gray-100 shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-500 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            aria-label="Confirm and sign acceptance"
            onClick={handleEsignSubmit}
            disabled={actionPending || !esignChecked}
            className="flex-1 rounded-lg px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50"
            style={{ backgroundColor: branding.accent_color, outlineColor: branding.accent_color }}
          >
            {actionPending ? 'Signing...' : 'Accept & Sign'}
          </button>
        </ModalFooter>
      </Modal>

      {/* Reject Modal */}
      <Modal
        isOpen={showRejectModal}
        onClose={() => setShowRejectModal(false)}
        title="Reject Quote"
        description="Please provide your email address to confirm the rejection."
        size="sm"
        closeOnOverlayClick={!actionPending}
      >
        {rejectError && (
          <div
            role="alert"
            aria-live="polite"
            className="mb-4 rounded-md bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-700 dark:text-red-300"
          >
            {rejectError}
          </div>
        )}

        <div>
          <label
            htmlFor="reject-email"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            Email Address
          </label>
          <input
            id="reject-email"
            type="email"
            name="reject_email"
            autoComplete="email"
            inputMode="email"
            spellCheck={false}
            value={rejectEmail}
            onChange={(e) => setRejectEmail(e.target.value)}
            placeholder="jane@company.com..."
            className="block w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-0"
            style={{ outlineColor: branding.primary_color }}
          />
        </div>

        <ModalFooter>
          <button
            type="button"
            aria-label="Cancel rejection"
            onClick={() => setShowRejectModal(false)}
            disabled={actionPending}
            className="flex-1 rounded-lg bg-white dark:bg-gray-700 px-4 py-2.5 text-sm font-semibold text-gray-900 dark:text-gray-100 shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-500 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleRejectSubmit}
            disabled={actionPending}
            className="flex-1 rounded-lg bg-red-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-red-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600 disabled:opacity-50"
          >
            {actionPending ? 'Rejecting...' : 'Confirm Rejection'}
          </button>
        </ModalFooter>
      </Modal>
    </div>
  );
}

export default PublicQuoteView;

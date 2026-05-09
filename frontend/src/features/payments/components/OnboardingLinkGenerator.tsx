import { useState } from 'react';
import { Button } from '../../../components/ui';
import { useCreateOnboardingLink, useStripeCustomers } from '../../../hooks/usePayments';
import { showSuccess, showError } from '../../../utils/toast';
import { extractApiErrorDetail } from '../../../utils/errors';

interface OnboardingLinkGeneratorProps {
  contactId?: number;
  companyId?: number;
  contactEmail?: string;
  onSendViaEmail?: (link: string) => void;
}

export function OnboardingLinkGenerator({
  contactId,
  companyId,
  contactEmail,
  onSendViaEmail,
}: OnboardingLinkGeneratorProps) {
  const [generatedLink, setGeneratedLink] = useState('');
  const linkMutation = useCreateOnboardingLink();

  // Check if this contact/company already has a Stripe customer.
  // Filtered server-side so we don't pull every customer in the
  // tenant just to filter client-side — the previous page_size=200
  // also exceeded the endpoint's hard cap of 100 and 422'd in prod.
  //
  // Send BOTH ids when present so the backend OR's them — a Stripe
  // customer may be linked at the company level only, and a
  // contact-only filter would miss an actually-onboarded business
  // and falsely flash "no payment method" on the badge.
  let lookupParams: { contact_id?: number; company_id?: number; page_size: number } | undefined;
  if (contactId || companyId) {
    lookupParams = { page_size: 1 };
    if (contactId) lookupParams.contact_id = contactId;
    if (companyId) lookupParams.company_id = companyId;
  }
  const { data: customersData } = useStripeCustomers(lookupParams);
  const hasPaymentMethod = (customersData?.total ?? 0) > 0;

  const handleGenerateLink = async () => {
    try {
      const result = await linkMutation.mutateAsync({
        contact_id: contactId,
        company_id: companyId,
        success_url: `${window.location.origin}/payments?setup=success`,
        cancel_url: `${window.location.origin}/payments?setup=canceled`,
      });
      setGeneratedLink(result.url);
    } catch (err) {
      // Surface the backend reason instead of a generic toast — the
      // mutation can fail for distinct reasons (403 access-denied,
      // 400 missing-id, Stripe outage, rate limit) and they all need
      // different remediation by the user.
      showError(extractApiErrorDetail(err) ?? 'Failed to generate payment setup link');
    }
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(generatedLink);
      showSuccess('Link copied to clipboard');
    } catch (err) {
      // Clipboard failures (permission denied, doc not focused,
      // unsupported in iframes) are user-actionable; the underlying
      // error name is enough context.
      const detail = err instanceof Error ? err.message : null;
      showError(detail ? `Failed to copy link: ${detail}` : 'Failed to copy link');
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 sm:p-6 border border-transparent dark:border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
          Payment Setup
        </h3>
        {hasPaymentMethod ? (
          <span className="inline-flex items-center rounded-full bg-green-100 dark:bg-green-900/30 px-2.5 py-0.5 text-xs font-medium text-green-800 dark:text-green-300">
            Payment method on file
          </span>
        ) : (
          <span className="inline-flex items-center rounded-full bg-gray-100 dark:bg-gray-700 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:text-gray-400">
            No payment method
          </span>
        )}
      </div>

      {!generatedLink ? (
        <Button
          variant="secondary"
          onClick={handleGenerateLink}
          isLoading={linkMutation.isPending}
          aria-label="Generate payment setup link"
          className="w-full sm:w-auto"
        >
          Get Payment Setup Link
        </Button>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <label htmlFor="onboarding-link" className="sr-only">Payment setup link</label>
            <input
              id="onboarding-link"
              type="text"
              value={generatedLink}
              readOnly
              className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm text-xs sm:text-sm focus-visible:outline-none focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500"
              autoComplete="off"
            />
          </div>
          <div className="flex flex-col sm:flex-row gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleCopy}
              aria-label="Copy payment setup link"
              className="flex-1 sm:flex-none"
            >
              Copy Link
            </Button>
            {onSendViaEmail && contactEmail && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => onSendViaEmail(generatedLink)}
                aria-label="Send payment setup link via email"
                className="flex-1 sm:flex-none"
              >
                Send via Email
              </Button>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={handleGenerateLink}
              isLoading={linkMutation.isPending}
              aria-label="Generate a new payment setup link"
              className="flex-1 sm:flex-none"
            >
              Regenerate
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

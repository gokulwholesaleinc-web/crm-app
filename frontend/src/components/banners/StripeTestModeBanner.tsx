import { useStripeMode } from '../../hooks/useStripeMode';

export function StripeTestModeBanner() {
  const { mode, isLoading } = useStripeMode();

  if (isLoading || mode !== 'test') return null;

  return (
    <div
      role="alert"
      aria-live="polite"
      className="flex items-center gap-2 rounded-md border border-yellow-300 bg-yellow-50 px-4 py-2 text-sm text-yellow-800 dark:border-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-300"
    >
      <span aria-hidden="true">⚠</span>
      <span className="whitespace-nowrap sm:whitespace-normal">
        Stripe is in <strong>TEST MODE</strong> &mdash; invoices will be created in Stripe test
        environment and customer emails are <strong>NOT</strong> delivered to real inboxes. Switch
        to live keys before sending real invoices.
      </span>
    </div>
  );
}

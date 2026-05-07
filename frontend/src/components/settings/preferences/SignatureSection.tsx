import type { PreferencesSectionProps } from './DensitySection';

export function SignatureSection(_props: PreferencesSectionProps) {
  return (
    <section aria-labelledby="prefs-signature-heading">
      <h3
        id="prefs-signature-heading"
        className="text-sm font-semibold text-gray-900 dark:text-gray-100"
      >
        Email signature
      </h3>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        Coming soon — auto-append a signature to new emails.
      </p>
    </section>
  );
}

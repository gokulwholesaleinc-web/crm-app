import type { PreferencesSectionProps } from './DensitySection';

const inputClass =
  'mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 shadow-sm text-sm focus-visible:outline-none focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500';

export function SignatureSection({ draft, setDraft }: PreferencesSectionProps) {
  const signature = draft.signature ?? '';
  const preview = signature ? `\n\n--\n${signature}` : '';

  return (
    <section aria-labelledby="prefs-signature-heading">
      <h3
        id="prefs-signature-heading"
        className="text-sm font-semibold text-gray-900 dark:text-gray-100"
      >
        Email signature
      </h3>
      <label
        htmlFor="prefs-signature-textarea"
        className="mt-2 block text-xs font-medium text-gray-700 dark:text-gray-300"
      >
        Signature
      </label>
      <textarea
        id="prefs-signature-textarea"
        name="signature"
        rows={6}
        value={signature}
        onChange={(e) => setDraft('signature', e.target.value)}
        className={inputClass}
        placeholder={'Jane Doe\nAccount Manager\njane@example.com...'}
        spellCheck={false}
      />
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        Auto-appended to new emails (not replies). Separated by a{' '}
        <code className="rounded bg-gray-100 dark:bg-gray-800 px-1 py-0.5 text-[0.7rem]">
          --
        </code>{' '}
        line.
      </p>
      {signature && (
        <div className="mt-3">
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300">
            Preview (appended to body)
          </p>
          <pre className="mt-1 whitespace-pre-wrap rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/60 px-3 py-2 text-xs font-mono text-gray-800 dark:text-gray-200">
            {preview}
          </pre>
        </div>
      )}
    </section>
  );
}

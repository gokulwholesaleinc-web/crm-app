import type { DensityMode, UserPreferences } from '../../../hooks/useUserPreferences';

export interface PreferencesSectionProps {
  draft: UserPreferences;
  setDraft: <K extends keyof UserPreferences>(
    key: K,
    value: UserPreferences[K],
  ) => void;
}

const OPTIONS: ReadonlyArray<{
  value: DensityMode;
  label: string;
  description: string;
}> = [
  {
    value: 'comfortable',
    label: 'Comfortable',
    description: 'Default row spacing — easier to scan.',
  },
  {
    value: 'compact',
    label: 'Compact',
    description: 'Tighter rows — fit more on screen.',
  },
];

export function DensitySection({ draft, setDraft }: PreferencesSectionProps) {
  const current: DensityMode = draft.density ?? 'comfortable';

  return (
    <section aria-labelledby="prefs-density-heading">
      <h3
        id="prefs-density-heading"
        className="text-sm font-semibold text-gray-900 dark:text-gray-100"
      >
        Density
      </h3>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        Controls row spacing on list pages (contacts, leads, quotes, proposals,
        payments).
      </p>
      <fieldset className="mt-3">
        <legend className="sr-only">Row density</legend>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {OPTIONS.map((opt) => {
            const id = `prefs-density-${opt.value}`;
            const checked = current === opt.value;
            return (
              <label
                key={opt.value}
                htmlFor={id}
                className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                  checked
                    ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20'
                    : 'border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <input
                  id={id}
                  type="radio"
                  name="prefs-density"
                  value={opt.value}
                  checked={checked}
                  onChange={() => setDraft('density', opt.value)}
                  className="mt-0.5"
                />
                <span className="flex-1">
                  <span className="block text-sm font-medium text-gray-900 dark:text-gray-100">
                    {opt.label}
                  </span>
                  <span className="block text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    {opt.description}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>
    </section>
  );
}

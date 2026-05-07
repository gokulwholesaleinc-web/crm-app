import type { UserPreferences } from '../../../hooks/useUserPreferences';

export interface PreferencesSectionProps {
  draft: UserPreferences;
  setDraft: <K extends keyof UserPreferences>(
    key: K,
    value: UserPreferences[K],
  ) => void;
}

export function DensitySection(_props: PreferencesSectionProps) {
  return (
    <section aria-labelledby="prefs-density-heading">
      <h3
        id="prefs-density-heading"
        className="text-sm font-semibold text-gray-900 dark:text-gray-100"
      >
        Density
      </h3>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        Coming soon — control table row spacing across the app.
      </p>
    </section>
  );
}

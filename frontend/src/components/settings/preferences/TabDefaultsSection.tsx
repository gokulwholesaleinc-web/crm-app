import type { PreferencesSectionProps } from './DensitySection';

export function TabDefaultsSection(_props: PreferencesSectionProps) {
  return (
    <section aria-labelledby="prefs-tabs-heading">
      <h3
        id="prefs-tabs-heading"
        className="text-sm font-semibold text-gray-900 dark:text-gray-100"
      >
        Default tab on detail pages
      </h3>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        Coming soon — pick the tab that opens first on each entity type.
      </p>
    </section>
  );
}

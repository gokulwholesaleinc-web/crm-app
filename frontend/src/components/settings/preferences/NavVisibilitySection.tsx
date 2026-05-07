import type { PreferencesSectionProps } from './DensitySection';

export function NavVisibilitySection(_props: PreferencesSectionProps) {
  return (
    <section aria-labelledby="prefs-nav-heading">
      <h3
        id="prefs-nav-heading"
        className="text-sm font-semibold text-gray-900 dark:text-gray-100"
      >
        Sidebar items
      </h3>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        Coming soon — hide sidebar items you don&rsquo;t use.
      </p>
    </section>
  );
}

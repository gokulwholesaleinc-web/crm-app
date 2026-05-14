import { useEffect } from 'react';

/**
 * Strip the global `.dark` class from <html> while a public-facing
 * customer view is mounted, then restore it on unmount.
 *
 * Public proposal pages render with a light-only
 * palette (header chip, tenant `bg_color_light`, gold accents) and
 * intentionally do NOT have a dark variant. When a CRM employee is
 * signed in with dark mode active and previews one of these links in
 * the same tab, the `.dark` class on <html> would otherwise cascade in
 * and trigger every `dark:text-gray-*` variant on these pages — light
 * text on light background.
 *
 * A MutationObserver re-strips `.dark` if `useTheme` re-applies it
 * mid-mount (system `prefers-color-scheme` flip, theme toggle from
 * another tab via storage event, etc.) — without it the page would
 * silently flip back to dark colors with no recovery until navigation.
 * The captured `hadDark` snapshot is what we restore on unmount so the
 * rest of the CRM returns to the user's actual preference.
 *
 * Customers visiting the link from an external browser are unaffected
 * (the CRM never sets `.dark` for them); this hook is purely defensive
 * for the in-CRM preview case.
 */
export function useForceLightMode(): void {
  useEffect(() => {
    const root = document.documentElement;
    const hadDark = root.classList.contains('dark');
    root.classList.remove('dark');
    const observer = new MutationObserver(() => {
      if (root.classList.contains('dark')) root.classList.remove('dark');
    });
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });
    return () => {
      observer.disconnect();
      if (hadDark) root.classList.add('dark');
    };
  }, []);
}

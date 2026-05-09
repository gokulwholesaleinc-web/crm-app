/**
 * Persistence for the dashboard "viewing as" selector.
 *
 * Kept separate from the component so React Fast Refresh stays happy
 * (a single file may not mix component + non-component exports).
 */

const STORAGE_KEY = 'dashboardViewingAs:v1';

export type ViewingAsValue = number | null;

export function loadStoredViewingAs(): ViewingAsValue {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null || raw === '' || raw === 'null') return null;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function writeStoredViewingAs(value: ViewingAsValue): void {
  try {
    if (value === null) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, String(value));
    }
  } catch {
    // Quota or disabled — silently drop. The selection still applies
    // for this tab via parent state; only persistence is lost.
  }
}

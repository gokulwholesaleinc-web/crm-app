import type { UserPreferences } from '../../../hooks/useUserPreferences';

/**
 * Shared props every preference section receives. The section reads its
 * own slice from `draft` and writes back via `setDraft(key, value)`. The
 * modal is the only place that knows the slice composition; sections
 * stay independent of each other.
 */
export interface PreferencesSectionProps {
  draft: UserPreferences;
  setDraft: <K extends keyof UserPreferences>(
    key: K,
    value: UserPreferences[K],
  ) => void;
}

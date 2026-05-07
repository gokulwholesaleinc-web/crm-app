import { useCallback, useEffect, useState } from 'react';
import { safeStorage } from '../utils/safeStorage';
import { useAuthStore } from '../store/authStore';

export type DensityMode = 'compact' | 'comfortable';
export type SortDirection = 'asc' | 'desc';

export type EntityKindWithTabs = 'contact' | 'lead' | 'opportunity' | 'company';
export type ListPageKey =
  | 'contacts'
  | 'leads'
  | 'quotes'
  | 'proposals'
  | 'payments';

export interface ListPageDefaults {
  pageSize?: number;
  sortBy?: string;
  sortDir?: SortDirection;
}

export interface UserPreferences {
  density?: DensityMode;
  tabDefaults?: Partial<Record<EntityKindWithTabs, string>>;
  hiddenNavIds?: string[];
  signature?: string;
  listDefaults?: Partial<Record<ListPageKey, ListPageDefaults>>;
}

const VERSION = 'v1';
const PREFS_EVENT = 'crm-user-prefs-changed';

function buildKey(userId: number | string | null | undefined): string | null {
  if (userId === null || userId === undefined || userId === '') return null;
  return `crm_prefs:${userId}:${VERSION}`;
}

function readRaw(userId: number | string | null | undefined): UserPreferences {
  const key = buildKey(userId);
  if (!key) return {};
  return safeStorage.getJson<UserPreferences>(key) ?? {};
}

function writeRaw(
  userId: number | string | null | undefined,
  prefs: UserPreferences,
): void {
  const key = buildKey(userId);
  if (!key) return;
  safeStorage.setJson(key, prefs);
}

function notifyChange(): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new Event(PREFS_EVENT));
}

export interface UseUserPreferencesResult {
  prefs: UserPreferences;
  setPref: <K extends keyof UserPreferences>(
    key: K,
    value: UserPreferences[K],
  ) => void;
  setMany: (partial: Partial<UserPreferences>) => void;
  clearListDefaults: (page: ListPageKey) => void;
}

/**
 * Per-user preference store backed by localStorage at
 * `crm_prefs:{userId}:v1`. Each setter merges into the latest blob from
 * disk, so concurrent updates from sibling components don't clobber.
 *
 * In-tab updates go through a window-level CustomEvent; cross-tab updates
 * arrive via `storage`. Both fall through to a re-read of disk so the
 * in-memory snapshot always reflects what's persisted.
 */
export function useUserPreferences(): UseUserPreferencesResult {
  const userId = useAuthStore((s) => s.user?.id);
  const [prefs, setPrefs] = useState<UserPreferences>(() => readRaw(userId));

  useEffect(() => {
    setPrefs(readRaw(userId));
  }, [userId]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const handler = () => setPrefs(readRaw(userId));
    window.addEventListener(PREFS_EVENT, handler);
    window.addEventListener('storage', handler);
    return () => {
      window.removeEventListener(PREFS_EVENT, handler);
      window.removeEventListener('storage', handler);
    };
  }, [userId]);

  const setPref = useCallback(
    <K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) => {
      const latest = readRaw(userId);
      const next: UserPreferences = { ...latest, [key]: value };
      writeRaw(userId, next);
      setPrefs(next);
      notifyChange();
    },
    [userId],
  );

  const setMany = useCallback(
    (partial: Partial<UserPreferences>) => {
      const latest = readRaw(userId);
      const next: UserPreferences = { ...latest, ...partial };
      writeRaw(userId, next);
      setPrefs(next);
      notifyChange();
    },
    [userId],
  );

  const clearListDefaults = useCallback(
    (page: ListPageKey) => {
      const latest = readRaw(userId);
      const ld = { ...(latest.listDefaults ?? {}) };
      delete ld[page];
      const next: UserPreferences = { ...latest, listDefaults: ld };
      writeRaw(userId, next);
      setPrefs(next);
      notifyChange();
    },
    [userId],
  );

  return { prefs, setPref, setMany, clearListDefaults };
}

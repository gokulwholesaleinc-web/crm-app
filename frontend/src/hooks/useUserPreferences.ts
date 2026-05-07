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

const LIST_PAGE_KEYS: ReadonlySet<string> = new Set([
  'contacts',
  'leads',
  'quotes',
  'proposals',
  'payments',
]);

const ENTITY_KINDS_WITH_TABS: ReadonlySet<string> = new Set([
  'contact',
  'lead',
  'opportunity',
  'company',
]);

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

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v);
}

function sanitizeListDefaults(
  raw: unknown,
): UserPreferences['listDefaults'] | undefined {
  if (!isPlainObject(raw)) return undefined;
  const out: NonNullable<UserPreferences['listDefaults']> = {};
  for (const [pageKey, slice] of Object.entries(raw)) {
    if (!LIST_PAGE_KEYS.has(pageKey)) continue;
    if (!isPlainObject(slice)) continue;
    const cleaned: ListPageDefaults = {};
    const ps = slice.pageSize;
    if (
      typeof ps === 'number' &&
      Number.isFinite(ps) &&
      Number.isInteger(ps) &&
      ps > 0
    ) {
      cleaned.pageSize = ps;
    }
    if (typeof slice.sortBy === 'string' && slice.sortBy.length > 0) {
      cleaned.sortBy = slice.sortBy;
    }
    if (slice.sortDir === 'asc' || slice.sortDir === 'desc') {
      cleaned.sortDir = slice.sortDir;
    }
    if (Object.keys(cleaned).length > 0) {
      (out as Record<string, ListPageDefaults>)[pageKey] = cleaned;
    }
  }
  return Object.keys(out).length > 0 ? out : undefined;
}

function sanitizeTabDefaults(
  raw: unknown,
): UserPreferences['tabDefaults'] | undefined {
  if (!isPlainObject(raw)) return undefined;
  const out: NonNullable<UserPreferences['tabDefaults']> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (!ENTITY_KINDS_WITH_TABS.has(k)) continue;
    if (typeof v === 'string' && v.length > 0) {
      (out as Record<string, string>)[k] = v;
    }
  }
  return Object.keys(out).length > 0 ? out : undefined;
}

/**
 * Validate a parsed JSON blob from localStorage against the
 * UserPreferences shape, dropping any field that doesn't match. Manual
 * localStorage edits, schema drift between app versions, or a future
 * write bug would otherwise let untyped values flow downstream
 * (e.g., `pageSize: "abc"` reaching the API as `NaN`).
 */
function sanitizePrefs(raw: unknown): UserPreferences {
  if (!isPlainObject(raw)) return {};
  const cleaned: UserPreferences = {};
  if (raw.density === 'compact' || raw.density === 'comfortable') {
    cleaned.density = raw.density;
  }
  if (Array.isArray(raw.hiddenNavIds)) {
    const ids = raw.hiddenNavIds.filter(
      (x): x is string => typeof x === 'string' && x.length > 0,
    );
    if (ids.length > 0) cleaned.hiddenNavIds = ids;
  }
  if (typeof raw.signature === 'string') {
    cleaned.signature = raw.signature;
  }
  const td = sanitizeTabDefaults(raw.tabDefaults);
  if (td) cleaned.tabDefaults = td;
  const ld = sanitizeListDefaults(raw.listDefaults);
  if (ld) cleaned.listDefaults = ld;
  return cleaned;
}

function readRaw(userId: number | string | null | undefined): UserPreferences {
  const key = buildKey(userId);
  if (!key) return {};
  return sanitizePrefs(safeStorage.getJson<unknown>(key));
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

type PrefValue<K extends keyof UserPreferences> = UserPreferences[K];
type PrefUpdater<K extends keyof UserPreferences> = (
  prev: PrefValue<K> | undefined,
) => PrefValue<K> | undefined;

export interface UseUserPreferencesResult {
  prefs: UserPreferences;
  setPref: <K extends keyof UserPreferences>(
    key: K,
    value: PrefValue<K> | undefined | PrefUpdater<K>,
  ) => void;
  setMany: (partial: Partial<UserPreferences>) => void;
}

/**
 * Per-user preference store backed by localStorage at
 * `crm_prefs:{userId}:v1`. Each setter merges into the latest blob from
 * disk, so concurrent updates from sibling components don't clobber.
 *
 * `setPref` accepts either a plain value or an updater function; the
 * updater receives the latest on-disk value for the key and returns the
 * new value. Use the updater form whenever the new value depends on the
 * old one (atomic merge) — the plain-value form can race with another
 * tab's write since React-state snapshots may be stale.
 *
 * In-tab updates fan out via a window-level CustomEvent; cross-tab
 * updates arrive via the `storage` event filtered to our own key.
 */
export function useUserPreferences(): UseUserPreferencesResult {
  const userId = useAuthStore((s) => s.user?.id);
  const [prefs, setPrefs] = useState<UserPreferences>(() => readRaw(userId));

  useEffect(() => {
    setPrefs(readRaw(userId));
  }, [userId]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const ourKey = buildKey(userId);
    const customHandler = () => setPrefs(readRaw(userId));
    const storageHandler = (e: StorageEvent) => {
      // Only react to our own pref key — ignore unrelated localStorage
      // writes (auth tokens, theme, etc.) so list pages don't churn on
      // every cross-tab write.
      if (e.key && e.key !== ourKey) return;
      setPrefs(readRaw(userId));
    };
    window.addEventListener(PREFS_EVENT, customHandler);
    window.addEventListener('storage', storageHandler);
    return () => {
      window.removeEventListener(PREFS_EVENT, customHandler);
      window.removeEventListener('storage', storageHandler);
    };
  }, [userId]);

  const setPref = useCallback(
    <K extends keyof UserPreferences>(
      key: K,
      value: PrefValue<K> | undefined | PrefUpdater<K>,
    ) => {
      const latest = readRaw(userId);
      const resolved =
        typeof value === 'function'
          ? (value as PrefUpdater<K>)(latest[key])
          : value;
      const next: UserPreferences = { ...latest, [key]: resolved };
      // Drop the key entirely when the resolved value is undefined so the
      // sanitizer's optional-field invariants stay clean across reloads.
      if (resolved === undefined) {
        delete (next as Record<string, unknown>)[key as string];
      }
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

  return { prefs, setPref, setMany };
}

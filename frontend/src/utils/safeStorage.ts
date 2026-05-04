/**
 * localStorage wrapper that swallows errors from private-mode browsers,
 * exhausted quota, or sandboxed iframes — every read returns null and
 * writes are no-ops in those cases.
 *
 * Use this anywhere you'd otherwise wrap localStorage in try/catch.
 * The JSON helpers also catch SyntaxError on malformed payloads, so a
 * corrupted entry from an older app version returns null instead of
 * crashing the call site.
 */
export const safeStorage = {
  get(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },

  set(key: string, value: string): void {
    try {
      localStorage.setItem(key, value);
    } catch {
      // unavailable, blocked, or quota exceeded — preference stays in-memory
    }
  },

  remove(key: string): void {
    try {
      localStorage.removeItem(key);
    } catch {
      // unavailable or blocked
    }
  },

  getJson<T>(key: string): T | null {
    const raw = safeStorage.get(key);
    if (raw === null) return null;
    try {
      return JSON.parse(raw) as T;
    } catch {
      return null;
    }
  },

  setJson(key: string, value: unknown): void {
    try {
      safeStorage.set(key, JSON.stringify(value));
    } catch {
      // circular reference or serialization failure
    }
  },
};

import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { useUserPreferences } from '../../hooks/useUserPreferences';
import { useAuthStore, type User } from '../../store/authStore';
import { markGuideCompleted } from './guideProgress';

const TEST_USER: User = {
  id: 42,
  email: 'rep@example.com',
  full_name: 'Rep User',
  is_active: true,
  is_superuser: false,
  role: 'sales_rep',
  created_at: '2026-05-18T00:00:00.000Z',
};

function Harness() {
  const { prefs, setPref } = useUserPreferences();
  const completed = prefs.guideProgress?.completedGuideIds?.join(',') || 'none';

  return (
    <button
      type="button"
      onClick={() => setPref('guideProgress', (prev) => markGuideCompleted(prev, 'dashboard-tour'))}
    >
      {completed}
    </button>
  );
}

function installMemoryStorage() {
  const store = new Map<string, string>();
  const storage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
  };
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    writable: true,
    value: storage,
  });
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    writable: true,
    value: storage,
  });
  return storage;
}

describe('guide completion fallback cache', () => {
  let storage: ReturnType<typeof installMemoryStorage>;

  beforeEach(() => {
    storage = installMemoryStorage();
    storage.clear();
    act(() => {
      useAuthStore.setState({
        user: TEST_USER,
        token: 'token',
        isAuthenticated: true,
        isLoading: false,
      });
    });
  });

  it('caches completed guide ids in per-user preferences for offline/local fallback', async () => {
    const user = userEvent.setup();
    const { unmount } = render(<Harness />);

    await user.click(screen.getByRole('button', { name: 'none' }));

    expect(storage.getItem('crm_prefs:42:v1')).toContain('dashboard-tour');
    expect(screen.getByRole('button', { name: 'dashboard-tour' })).toBeInTheDocument();

    unmount();
    render(<Harness />);

    expect(screen.getByRole('button', { name: 'dashboard-tour' })).toBeInTheDocument();
  });
});

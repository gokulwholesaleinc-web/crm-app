/**
 * Admin/manager-only dashboard scope switcher. Selection persists in
 * localStorage; ``null`` means tenant-wide rollup, a numeric id scopes
 * to that user. Sales reps never see this control — the backend's
 * ``effective_owner_id`` would coerce their request back to self
 * anyway.
 */

import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listUsers } from '../../../api/auth';
import { useAuthStore } from '../../../store/authStore';
import { writeStoredViewingAs, type ViewingAsValue } from './viewingAsStorage';

interface Props {
  value: ViewingAsValue;
  onChange: (next: ViewingAsValue) => void;
}

export function ViewingAsSelector({ value, onChange }: Props) {
  const user = useAuthStore((s) => s.user);
  const privileged = user?.is_superuser || user?.role === 'admin' || user?.role === 'manager';

  // Only fetch the user list when the control will actually render.
  const { data: users } = useQuery({
    queryKey: ['auth', 'users', 'dashboard-switcher'],
    queryFn: () => listUsers(0, 200),
    enabled: privileged,
    staleTime: 5 * 60 * 1000,
  });

  // If the persisted owner_id no longer matches an active user (deleted,
  // deactivated), reset to tenant-wide so the dropdown doesn't show a
  // stale value with empty numbers underneath.
  useEffect(() => {
    if (value === null || !users) return;
    if (!users.some((u) => u.id === value && u.is_active)) {
      onChange(null);
    }
  }, [value, users, onChange]);

  const sortedUsers = useMemo(
    () => (users ?? []).filter((u) => u.is_active).sort((a, b) => a.full_name.localeCompare(b.full_name)),
    [users],
  );

  if (!privileged) {
    return null;
  }

  return (
    <label className="flex items-center gap-2 text-xs sm:text-sm text-gray-600 dark:text-gray-400">
      <span className="whitespace-nowrap">Viewing as</span>
      <select
        value={value ?? ''}
        onChange={(e) => {
          const next = e.target.value === '' ? null : Number(e.target.value);
          writeStoredViewingAs(next);
          onChange(next);
        }}
        className="rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1 text-xs sm:text-sm text-gray-900 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
        aria-label="Scope dashboard to a specific user (admin only)"
      >
        <option value="">Everyone (tenant)</option>
        {sortedUsers.map((u) => (
          <option key={u.id} value={u.id}>
            {u.full_name || u.email}
          </option>
        ))}
      </select>
    </label>
  );
}

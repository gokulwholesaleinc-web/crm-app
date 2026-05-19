import { describe, expect, it } from 'vitest';

import { canSeeSecondaryNavItem } from './navigation.config';

describe('canSeeSecondaryNavItem', () => {
  it('allows managers to access duplicate cleanup without exposing admin-only pages', () => {
    const manager = { role: 'manager', is_superuser: false };

    expect(canSeeSecondaryNavItem('admin-dedup', manager)).toBe(true);
    expect(canSeeSecondaryNavItem('admin', manager)).toBe(false);
    expect(canSeeSecondaryNavItem('approvals', manager)).toBe(false);
  });

  it('allows admins and superusers to access admin navigation', () => {
    expect(canSeeSecondaryNavItem('admin', { role: 'admin', is_superuser: false })).toBe(true);
    expect(canSeeSecondaryNavItem('admin-dedup', { role: 'sales_rep', is_superuser: true })).toBe(true);
  });

  it('hides duplicate cleanup from non-manager roles', () => {
    expect(canSeeSecondaryNavItem('admin-dedup', { role: 'sales_rep', is_superuser: false })).toBe(false);
    expect(canSeeSecondaryNavItem('settings', { role: 'viewer', is_superuser: false })).toBe(true);
  });
});

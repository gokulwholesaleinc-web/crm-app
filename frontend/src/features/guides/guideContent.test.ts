import { describe, expect, it } from 'vitest';
import {
  GUIDE_REGISTRY,
  getGuidesForPath,
  getGuidesForRole,
  getRecommendedGuides,
  normalizeRole,
} from './guideContent';

describe('guide registry filtering', () => {
  it('returns role-specific recommendations for sales reps', () => {
    const ids = getRecommendedGuides('sales_rep').map((guide) => guide.id);

    expect(ids).toEqual([
      'dashboard-tour',
      'contacts-tour',
      'leads-tour',
      'pipeline-tour',
      'proposals-tour',
      'payments-tour',
      'activities-tour',
      'inbox-tour',
    ]);
  });

  it('keeps admin-only guides out of non-admin roles', () => {
    expect(getGuidesForPath('/admin/user-approvals', 'manager')).toHaveLength(0);
    expect(getGuidesForPath('/admin/sharing', 'manager')).toHaveLength(0);
    expect(getGuidesForRole('manager').filter((guide) => guide.path.startsWith('/admin')))
      .toHaveLength(0);
    expect(getGuidesForPath('/admin/user-approvals', 'admin').map((guide) => guide.id))
      .toContain('user-approvals-tour');
  });

  it('keeps admin parent tours from bleeding into admin child pages', () => {
    expect(getGuidesForPath('/admin/user-approvals', 'admin').map((guide) => guide.id))
      .toEqual(['user-approvals-tour']);
    expect(getGuidesForPath('/admin/sharing', 'admin').map((guide) => guide.id))
      .toEqual(['admin-sharing-tour']);
  });

  it('does not show list-page guides on detail routes', () => {
    expect(getGuidesForPath('/contacts/123', 'sales_rep')).toHaveLength(0);
    expect(getGuidesForPath('/leads/123', 'sales_rep')).toHaveLength(0);
    expect(getGuidesForPath('/proposals/123', 'sales_rep')).toHaveLength(0);
    expect(getGuidesForPath('/payments/123', 'sales_rep')).toHaveLength(0);
  });

  it('splits personal settings from admin-only settings guidance', () => {
    const viewerSettings = getGuidesForPath('/settings', 'viewer').map((guide) => guide.id);
    const adminSettings = getGuidesForPath('/settings', 'admin').map((guide) => guide.id);

    expect(viewerSettings).toContain('settings-preferences-tour');
    expect(viewerSettings).not.toContain('settings-admin-tour');
    expect(adminSettings).toContain('settings-preferences-tour');
    expect(adminSettings).toContain('settings-admin-tour');
  });

  it('keeps every /admin guide admin-only', () => {
    for (const guide of GUIDE_REGISTRY.filter((entry) => entry.path.startsWith('/admin'))) {
      expect(guide.roles).toEqual(['admin']);
    }
  });

  it('limits viewer guides to read-oriented tours', () => {
    const ids = getGuidesForRole('viewer').map((guide) => guide.id);

    expect(ids).toContain('navigation-basics');
    expect(ids).toContain('reports-tour');
    expect(ids).not.toContain('payments-tour');
    expect(ids).not.toContain('user-approvals-tour');
  });

  it('normalizes unknown roles safely', () => {
    expect(normalizeRole(undefined)).toBe('viewer');
    expect(normalizeRole('sales_rep')).toBe('sales_rep');
    expect(normalizeRole('viewer', true)).toBe('admin');
  });
});

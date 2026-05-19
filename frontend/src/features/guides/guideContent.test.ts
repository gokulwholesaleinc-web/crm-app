import { describe, expect, it } from 'vitest';
import {
  GUIDE_REGISTRY,
  getGuidesForPath,
  getGuidesForRole,
  getRecommendedGuides,
  guideMatchesPath,
  normalizeRole,
  type GuideRole,
} from './guideContent';

const guideIdsForPath = (path: string, role: GuideRole) =>
  getGuidesForPath(path, role).map((guide) => guide.id);

const guideById = (id: string) => {
  const guide = GUIDE_REGISTRY.find((entry) => entry.id === id);
  if (!guide) {
    throw new Error(`Missing guide ${id}`);
  }
  return guide;
};

describe('guide registry filtering', () => {
  it('returns role-specific recommendations for sales reps', () => {
    const ids = getRecommendedGuides('sales_rep').map((guide) => guide.id);

    expect(ids).toEqual([
      'dashboard-tour',
      'contacts-tour',
      'companies-tour',
      'leads-tour',
      'pipeline-tour',
      'proposals-tour',
      'payments-tour',
      'activities-tour',
      'inbox-tour',
    ]);
  });

  it('keeps admin-only guides out of managers', () => {
    expect(getGuidesForPath('/admin/user-approvals', 'manager')).toHaveLength(0);
    expect(getGuidesForPath('/admin/sharing', 'manager')).toHaveLength(0);
    expect(getGuidesForPath('/admin/dedup', 'manager')).toHaveLength(0);
    expect(guideIdsForPath('/settings', 'manager')).not.toContain('settings-admin-tour');
    expect(getGuidesForRole('manager').filter((guide) => guide.path.startsWith('/admin')).map((guide) => guide.id))
      .toEqual([]);
    expect(getGuidesForPath('/admin/user-approvals', 'admin').map((guide) => guide.id))
      .toContain('user-approvals-tour');
    expect(guideIdsForPath('/settings', 'admin')).toContain('settings-admin-tour');
  });

  it('keeps admin parent tours from bleeding into admin child pages', () => {
    expect(getGuidesForPath('/admin/user-approvals', 'admin').map((guide) => guide.id))
      .toEqual(['user-approvals-tour']);
    expect(getGuidesForPath('/admin/sharing', 'admin').map((guide) => guide.id))
      .toEqual(['admin-sharing-tour']);
  });

  it('covers list and detail company routes', () => {
    expect(guideIdsForPath('/companies', 'sales_rep')).toEqual(['companies-tour']);
    expect(guideIdsForPath('/companies/42', 'sales_rep')).toEqual(['company-detail-tour']);
    expect(guideIdsForPath('/companies/42', 'viewer')).toEqual(['company-detail-tour']);
  });

  it('covers major detail routes with dedicated tours', () => {
    expect(guideIdsForPath('/contacts/123', 'sales_rep')).toEqual(['contact-detail-tour']);
    expect(guideIdsForPath('/companies/123', 'sales_rep')).toEqual(['company-detail-tour']);
    expect(guideIdsForPath('/leads/123', 'sales_rep')).toEqual(['lead-detail-tour']);
    expect(guideIdsForPath('/proposals/123', 'sales_rep')).toEqual(['proposal-detail-tour']);
    expect(guideIdsForPath('/payments/123', 'sales_rep')).toEqual(['payment-detail-tour']);
    expect(guideIdsForPath('/campaigns/123', 'manager')).toEqual(['campaign-detail-tour']);
  });

  it('role-gates staff and manager detail guides', () => {
    expect(guideIdsForPath('/leads/123', 'viewer')).toEqual([]);
    expect(guideIdsForPath('/proposals/123', 'viewer')).toEqual([]);
    expect(guideIdsForPath('/payments/123', 'viewer')).toEqual([]);
    expect(guideIdsForPath('/campaigns/123', 'sales_rep')).toEqual([]);
    expect(guideIdsForPath('/campaigns/123', 'manager')).toEqual(['campaign-detail-tour']);
    expect(guideIdsForPath('/campaigns/123', 'admin')).toEqual(['campaign-detail-tour']);
  });

  it('does not show stale parent or list-page guides on detail routes', () => {
    expect(guideIdsForPath('/contacts/123', 'sales_rep')).not.toContain('contacts-tour');
    expect(guideIdsForPath('/companies/123', 'sales_rep')).not.toContain('companies-tour');
    expect(guideIdsForPath('/leads/123', 'sales_rep')).not.toContain('leads-tour');
    expect(guideIdsForPath('/proposals/123', 'sales_rep')).not.toContain('proposals-tour');
    expect(guideIdsForPath('/payments/123', 'sales_rep')).not.toContain('payments-tour');
    expect(guideIdsForPath('/campaigns/123', 'manager')).not.toContain('campaigns-tour');
  });

  it('matches exact and dynamic paths by full route segment', () => {
    const contactListGuide = guideById('contacts-tour');
    const contactDetailGuide = guideById('contact-detail-tour');
    const adminGuide = guideById('admin-dashboard-tour');

    expect(guideMatchesPath(contactListGuide, '/contacts')).toBe(true);
    expect(guideMatchesPath(contactListGuide, '/contacts/123')).toBe(false);
    expect(guideMatchesPath(contactDetailGuide, '/contacts/123')).toBe(true);
    expect(guideMatchesPath(contactDetailGuide, '/contacts')).toBe(false);
    expect(guideMatchesPath(contactDetailGuide, '/contacts/123/activity')).toBe(false);
    expect(guideMatchesPath(adminGuide, '/admin/user-approvals')).toBe(false);
    expect(getGuidesForPath('/companies-archive', 'sales_rep')).toEqual([]);
    expect(getGuidesForPath('/proposals/public/demo-token', 'sales_rep')).toEqual([]);
  });

  it('splits personal settings from admin-only settings guidance', () => {
    const viewerSettings = getGuidesForPath('/settings', 'viewer').map((guide) => guide.id);
    const adminSettings = getGuidesForPath('/settings', 'admin').map((guide) => guide.id);

    expect(viewerSettings).toContain('settings-preferences-tour');
    expect(viewerSettings).not.toContain('settings-admin-tour');
    expect(adminSettings).toContain('settings-preferences-tour');
    expect(adminSettings).toContain('settings-admin-tour');
  });

  it('keeps admin pages admin-only', () => {
    const adminGuideIds = new Set([
      'settings-admin-tour',
      'admin-dashboard-tour',
      'user-approvals-tour',
      'admin-sharing-tour',
      'duplicate-cleanup-tour',
    ]);

    for (const guide of GUIDE_REGISTRY.filter((entry) => (
      adminGuideIds.has(entry.id)
    ))) {
      expect(guide.roles).toEqual(['admin']);
    }

    expect(guideById('admin-sharing-tour').roles).toEqual(['admin']);
    expect(guideById('duplicate-cleanup-tour').roles).toEqual(['admin']);
  });

  it('limits viewer guides to read-oriented tours', () => {
    const ids = getGuidesForRole('viewer').map((guide) => guide.id);

    expect(ids).toContain('navigation-basics');
    expect(ids).toContain('companies-tour');
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

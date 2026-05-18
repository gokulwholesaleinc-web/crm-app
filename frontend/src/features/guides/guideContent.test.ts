import { describe, expect, it } from 'vitest';
import {
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
    expect(getGuidesForPath('/admin/user-approvals', 'admin').map((guide) => guide.id))
      .toContain('user-approvals-tour');
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

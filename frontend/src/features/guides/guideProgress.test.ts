import { describe, expect, it } from 'vitest';
import {
  disableGuides,
  enableGuides,
  fromAccountGuideProgress,
  guideProgressKey,
  isGuideCompleted,
  markGuideCompleted,
  resetGuideProgress,
  toAccountGuideProgress,
} from './guideProgress';

describe('guide progress helpers', () => {
  it('marks guide completion idempotently', () => {
    const progress = markGuideCompleted(
      { completedGuideIds: ['dashboard-tour'] },
      'contacts-tour',
    );
    const again = markGuideCompleted(progress, 'contacts-tour');

    expect(isGuideCompleted(again, 'contacts-tour')).toBe(true);
    expect(again.completedGuideIds).toEqual(['contacts-tour', 'dashboard-tour']);
  });

  it('can disable, re-enable, and reset guide state for refreshers', () => {
    const disabled = disableGuides({ completedGuideIds: ['dashboard-tour'] }, '2026-05-18T00:00:00.000Z');

    expect(disabled.disabledAt).toBe('2026-05-18T00:00:00.000Z');
    expect(enableGuides(disabled).disabledAt).toBeUndefined();
    expect(resetGuideProgress(disabled, '2026-05-18T01:00:00.000Z')).toEqual({
      completedGuideIds: [],
      firstRunDismissedAt: undefined,
      disabledAt: undefined,
      lastResetAt: '2026-05-18T01:00:00.000Z',
    });
  });

  it('maps account preference payloads to local guide state', () => {
    const local = fromAccountGuideProgress({
      completed_guide_ids: ['pipeline-tour', 'dashboard-tour', 'pipeline-tour'],
      first_run_dismissed_at: '2026-05-18T20:00:00.000Z',
      disabled_at: null,
      last_reset_at: null,
    });

    expect(local).toEqual({
      completedGuideIds: ['dashboard-tour', 'pipeline-tour'],
      firstRunDismissedAt: '2026-05-18T20:00:00.000Z',
    });
    expect(toAccountGuideProgress(local)).toEqual({
      completed_guide_ids: ['dashboard-tour', 'pipeline-tour'],
      first_run_dismissed_at: '2026-05-18T20:00:00.000Z',
      disabled_at: null,
      last_reset_at: null,
    });
    expect(guideProgressKey(local)).toBe(guideProgressKey(fromAccountGuideProgress(toAccountGuideProgress(local))));
  });
});

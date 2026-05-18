import type { AccountGuideProgress } from '../../api/account';

export interface GuideProgress {
  completedGuideIds?: string[];
  firstRunDismissedAt?: string;
  disabledAt?: string;
  lastResetAt?: string;
}

export function uniqueGuideIds(ids: readonly string[] | undefined): string[] {
  return Array.from(new Set((ids ?? []).filter(Boolean))).sort();
}

export function isGuideCompleted(
  progress: GuideProgress | undefined,
  guideId: string,
): boolean {
  return Boolean(progress?.completedGuideIds?.includes(guideId));
}

export function hasAnyGuideCompletion(progress: GuideProgress | undefined): boolean {
  return Boolean(progress?.completedGuideIds?.length);
}

export function hasGuideProgressState(progress: GuideProgress | undefined): boolean {
  return Boolean(
    progress?.completedGuideIds?.length ||
      progress?.firstRunDismissedAt ||
      progress?.disabledAt ||
      progress?.lastResetAt,
  );
}

export function markGuideCompleted(
  progress: GuideProgress | undefined,
  guideId: string,
): GuideProgress {
  return {
    ...progress,
    completedGuideIds: uniqueGuideIds([...(progress?.completedGuideIds ?? []), guideId]),
  };
}

export function disableGuides(
  progress: GuideProgress | undefined,
  at = new Date().toISOString(),
): GuideProgress {
  return {
    ...progress,
    disabledAt: at,
  };
}

export function enableGuides(progress: GuideProgress | undefined): GuideProgress {
  const next = { ...progress };
  delete next.disabledAt;
  return next;
}

export function resetGuideProgress(
  progress: GuideProgress | undefined,
  at = new Date().toISOString(),
): GuideProgress {
  return {
    ...progress,
    completedGuideIds: [],
    firstRunDismissedAt: undefined,
    disabledAt: undefined,
    lastResetAt: at,
  };
}

export function dismissFirstRunPrompt(
  progress: GuideProgress | undefined,
  at = new Date().toISOString(),
): GuideProgress {
  return {
    ...progress,
    firstRunDismissedAt: at,
  };
}

export function fromAccountGuideProgress(
  progress: AccountGuideProgress | null | undefined,
): GuideProgress | undefined {
  if (!progress) return undefined;
  const next: GuideProgress = {};
  const completedGuideIds = uniqueGuideIds(progress.completed_guide_ids);
  if (completedGuideIds.length > 0) {
    next.completedGuideIds = completedGuideIds;
  }
  if (progress.first_run_dismissed_at) {
    next.firstRunDismissedAt = progress.first_run_dismissed_at;
  }
  if (progress.disabled_at) {
    next.disabledAt = progress.disabled_at;
  }
  if (progress.last_reset_at) {
    next.lastResetAt = progress.last_reset_at;
  }
  return hasGuideProgressState(next) ? next : undefined;
}

export function toAccountGuideProgress(
  progress: GuideProgress | undefined,
): AccountGuideProgress {
  return {
    completed_guide_ids: uniqueGuideIds(progress?.completedGuideIds),
    first_run_dismissed_at: progress?.firstRunDismissedAt ?? null,
    disabled_at: progress?.disabledAt ?? null,
    last_reset_at: progress?.lastResetAt ?? null,
  };
}

export function guideProgressKey(progress: GuideProgress | undefined): string {
  return JSON.stringify(toAccountGuideProgress(progress));
}

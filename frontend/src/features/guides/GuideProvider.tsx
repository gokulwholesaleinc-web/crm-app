/* eslint-disable react-refresh/only-export-components -- this module exposes the guide hook plus a testable overlay alongside the provider. */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  AcademicCapIcon,
  CheckIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CursorArrowRaysIcon,
  ExclamationTriangleIcon,
  MapPinIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import clsx from 'clsx';
import {
  getGuideById,
  getGuidesForPath,
  getGuidesForRole,
  getRecommendedGuides,
  guideMatchesPath,
  normalizeRole,
  type Guide,
  type GuideRole,
  type GuideStep,
} from './guideContent';
import {
  disableGuides,
  dismissFirstRunPrompt,
  enableGuides,
  fromAccountGuideProgress,
  guideProgressKey,
  hasAnyGuideCompletion,
  hasGuideProgressState,
  isGuideCompleted,
  markGuideCompleted,
  resetGuideProgress,
  toAccountGuideProgress,
  type GuideProgress,
} from './guideProgress';
import { accountApi } from '../../api/account';
import { useAuthStore } from '../../store/authStore';
import { accountKeys, useAccountPreferences } from '../../hooks/useAccount';
import { useUserPreferences } from '../../hooks/useUserPreferences';
import { Button } from '../../components/ui/Button';
import { showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';

const EMPTY_COMPLETED_GUIDE_IDS: readonly string[] = [];

interface GuideContextValue {
  role: GuideRole;
  activeGuide: Guide | null;
  currentStepIndex: number;
  availableGuides: Guide[];
  currentPageGuides: Guide[];
  recommendedGuides: Guide[];
  completedGuideIds: readonly string[];
  guidesDisabled: boolean;
  startGuide: (guideId: string) => void;
  startBestGuide: () => void;
  closeGuide: () => void;
  completeGuide: () => void;
  dismissPrompt: () => void;
  setGuidesEnabled: (enabled: boolean) => void;
  resetProgress: () => void;
  isCompleted: (guideId: string) => boolean;
}

const GuideContext = createContext<GuideContextValue | null>(null);

export function useGuides(): GuideContextValue {
  const value = useContext(GuideContext);
  if (!value) {
    throw new Error('useGuides must be used inside GuideProvider');
  }
  return value;
}

export function GuideProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { prefs: localPrefs, setPref: setLocalPref } = useUserPreferences();
  const accountPrefsQuery = useAccountPreferences();
  const role = normalizeRole(user?.role, user?.is_superuser);
  const localGuideProgress = localPrefs.guideProgress;
  const accountGuideProgress = useMemo(
    () => fromAccountGuideProgress(accountPrefsQuery.data?.guide_progress),
    [accountPrefsQuery.data?.guide_progress],
  );
  const guideProgress = accountGuideProgress ?? localGuideProgress;
  const completedGuideIds = guideProgress?.completedGuideIds ?? EMPTY_COMPLETED_GUIDE_IDS;
  const guidesDisabled = Boolean(guideProgress?.disabledAt);
  const migratedLocalProgressRef = useRef<string | null>(null);
  const { mutate: syncGuideProgress } = useMutation({
    mutationFn: ({
      progress,
    }: {
      progress: GuideProgress;
      notifyOnError: boolean;
    }) =>
      accountApi.updateAccountPreferences({
        guide_progress: toAccountGuideProgress(progress),
      }),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(accountKeys.preferences(), data);
      const serverProgress = fromAccountGuideProgress(data.guide_progress);
      // Only mark the local-progress key as migrated once the server has
      // actually confirmed the write. Setting this before the mutate
      // fires (as the original code did) makes a failed sync permanent —
      // the migration effect short-circuits next time even though the
      // server never received the progress.
      migratedLocalProgressRef.current = guideProgressKey(
        serverProgress ?? variables.progress,
      );
      if (hasGuideProgressState(serverProgress)) {
        setLocalPref('guideProgress', serverProgress);
      }
    },
    onError: (error, variables) => {
      console.warn('[guides] failed to sync guide progress', error);
      if (variables.notifyOnError) {
        const detail = extractApiErrorDetail(error);
        showError(
          detail
            ? `Guide progress could not be saved: ${detail}`
            : 'Guide progress could not be saved to your account',
        );
      }
    },
  });

  const availableGuides = useMemo(() => getGuidesForRole(role), [role]);
  const currentPageGuides = useMemo(
    () => getGuidesForPath(location.pathname, role),
    [location.pathname, role],
  );
  const recommendedGuides = useMemo(() => getRecommendedGuides(role), [role]);
  const [activeGuideId, setActiveGuideId] = useState<string | null>(null);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const activeGuide = activeGuideId ? getGuideById(activeGuideId) ?? null : null;

  const closeGuide = useCallback(() => {
    setActiveGuideId(null);
    setCurrentStepIndex(0);
  }, []);

  useEffect(() => {
    if (!isAuthenticated || accountPrefsQuery.isLoading) {
      return;
    }

    // A failed GET (network blip, 500, expired auth) leaves `data`
    // undefined and `isError` set. Silently falling through here would
    // make the local cache the permanent source of truth with no signal
    // to the user, so surface it once instead of looping.
    if (accountPrefsQuery.isError || !accountPrefsQuery.data) {
      return;
    }

    if (hasGuideProgressState(accountGuideProgress)) {
      if (guideProgressKey(accountGuideProgress) !== guideProgressKey(localGuideProgress)) {
        setLocalPref('guideProgress', accountGuideProgress);
      }
      return;
    }

    const progressToMigrate = localGuideProgress;
    if (!hasGuideProgressState(progressToMigrate) || !progressToMigrate) {
      return;
    }

    const localKey = guideProgressKey(progressToMigrate);
    if (migratedLocalProgressRef.current === localKey) {
      return;
    }
    // NOTE: we do NOT set migratedLocalProgressRef.current here — the
    // mutation's onSuccess does, so a failed migration is retried on the
    // next navigation instead of being silently dropped forever.
    syncGuideProgress({
      progress: progressToMigrate,
      notifyOnError: false,
    });
  }, [
    accountGuideProgress,
    accountPrefsQuery.data,
    accountPrefsQuery.isError,
    accountPrefsQuery.isLoading,
    isAuthenticated,
    localGuideProgress,
    setLocalPref,
    syncGuideProgress,
  ]);

  const updateGuideProgress = useCallback(
    (updater: (prev: GuideProgress | undefined) => GuideProgress) => {
      // Use the functional setter so two rapid completions (e.g. clicking
      // Done on a multi-step tour) don't fight a stale-closure `prev`.
      let next: GuideProgress | undefined;
      setLocalPref('guideProgress', (prev) => {
        next = updater(prev);
        return next;
      });
      // `next` is set synchronously by the setter callback above.
      if (isAuthenticated && next) {
        // We DO NOT update migratedLocalProgressRef here. The mutation's
        // onSuccess does that after the server confirms the write, so a
        // failed sync stays retry-eligible instead of being marked done.
        syncGuideProgress({
          progress: next,
          notifyOnError: true,
        });
      }
    },
    [isAuthenticated, setLocalPref, syncGuideProgress],
  );

  const startGuide = useCallback(
    (guideId: string) => {
      const guide = getGuideById(guideId);
      if (!guide) {
        // Retired guide ID (server may still carry a completion for an
        // old guide) or an empty fallback from startBestGuide. Warn so
        // the launcher button doesn't look mysteriously dead.
        if (guideId) {
          console.warn('[guides] startGuide: unknown guide id', guideId);
        }
        return;
      }
      setActiveGuideId(guide.id);
      setCurrentStepIndex(0);
      if (!guideMatchesPath(guide, location.pathname)) {
        navigate(guide.path);
      }
    },
    [location.pathname, navigate],
  );

  const completeGuide = useCallback(() => {
    if (!activeGuide) return;
    updateGuideProgress((prev) => markGuideCompleted(prev, activeGuide.id));
    closeGuide();
  }, [activeGuide, closeGuide, updateGuideProgress]);

  const dismissPrompt = useCallback(() => {
    updateGuideProgress((prev) => dismissFirstRunPrompt(prev));
  }, [updateGuideProgress]);

  const setGuidesEnabled = useCallback(
    (enabled: boolean) => {
      updateGuideProgress((prev) => (enabled ? enableGuides(prev) : disableGuides(prev)));
      if (!enabled) {
        closeGuide();
      }
    },
    [closeGuide, updateGuideProgress],
  );

  const resetProgress = useCallback(() => {
    updateGuideProgress((prev) => resetGuideProgress(prev));
  }, [updateGuideProgress]);

  const isCompleted = useCallback(
    (guideId: string) => isGuideCompleted(guideProgress, guideId),
    [guideProgress],
  );

  const startBestGuide = useCallback(() => {
    const currentUnfinished = currentPageGuides.find((guide) => !isCompleted(guide.id));
    if (currentUnfinished) {
      startGuide(currentUnfinished.id);
      return;
    }
    const recommendedUnfinished = recommendedGuides.find((guide) => !isCompleted(guide.id));
    const best = recommendedUnfinished ?? recommendedGuides[0] ?? availableGuides[0];
    // If no guide is available for the user's role, the launcher should
    // not call us — but if a stale prompt path does, skip silently
    // instead of asking startGuide to look up an empty id.
    if (!best) return;
    startGuide(best.id);
  }, [availableGuides, currentPageGuides, isCompleted, recommendedGuides, startGuide]);

  const value = useMemo<GuideContextValue>(
    () => ({
      role,
      activeGuide,
      currentStepIndex,
      availableGuides,
      currentPageGuides,
      recommendedGuides,
      completedGuideIds,
      guidesDisabled,
      startGuide,
      startBestGuide,
      closeGuide,
      completeGuide,
      dismissPrompt,
      setGuidesEnabled,
      resetProgress,
      isCompleted,
    }),
    [
      activeGuide,
      availableGuides,
      closeGuide,
      completeGuide,
      completedGuideIds,
      currentPageGuides,
      currentStepIndex,
      dismissPrompt,
      guidesDisabled,
      isCompleted,
      recommendedGuides,
      resetProgress,
      role,
      setGuidesEnabled,
      startBestGuide,
      startGuide,
    ],
  );

  const showFirstRunPrompt =
    isAuthenticated &&
    (!accountPrefsQuery.isLoading || hasGuideProgressState(localGuideProgress)) &&
    !guidesDisabled &&
    !activeGuide &&
    !guideProgress?.firstRunDismissedAt &&
    !hasAnyGuideCompletion(guideProgress) &&
    recommendedGuides.length > 0 &&
    location.pathname !== '/help';

  return (
    <GuideContext.Provider value={value}>
      {children}
      {activeGuide && (
        <GuideTourOverlay
          guide={activeGuide}
          stepIndex={currentStepIndex}
          onStepChange={setCurrentStepIndex}
          onClose={closeGuide}
          onComplete={completeGuide}
        />
      )}
      {showFirstRunPrompt && (
        <GuideFirstRunPrompt
          role={role}
          onStart={startBestGuide}
          onDismiss={dismissPrompt}
        />
      )}
    </GuideContext.Provider>
  );
}

function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

type GuideStepTone = 'action' | 'target' | 'context' | 'missing';

const STEP_TONE_STYLES = {
  action: {
    label: 'Action step',
    Icon: CursorArrowRaysIcon,
    iconClass: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/25 dark:text-emerald-200',
    panelClass: 'border-emerald-200/80 dark:border-emerald-800/70',
    accentClass: 'bg-emerald-500',
    progressClass: 'bg-emerald-500',
    chipClass: 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/25 dark:text-emerald-200 dark:ring-emerald-800/70',
    actionClass: 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-800/70 dark:bg-emerald-900/20 dark:text-emerald-100',
  },
  target: {
    label: 'Focus step',
    Icon: MapPinIcon,
    iconClass: 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200',
    panelClass: 'border-primary-200/80 dark:border-primary-800/70',
    accentClass: 'bg-primary-500',
    progressClass: 'bg-primary-500',
    chipClass: 'bg-primary-50 text-primary-700 ring-primary-200 dark:bg-primary-900/30 dark:text-primary-200 dark:ring-primary-800/70',
    actionClass: 'border-primary-100 bg-primary-50 text-primary-800 dark:border-primary-900/40 dark:bg-primary-900/20 dark:text-primary-200',
  },
  context: {
    label: 'Context step',
    Icon: AcademicCapIcon,
    iconClass: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-200',
    panelClass: 'border-gray-200 dark:border-gray-700',
    accentClass: 'bg-gray-500',
    progressClass: 'bg-gray-500',
    chipClass: 'bg-gray-100 text-gray-700 ring-gray-200 dark:bg-gray-800 dark:text-gray-200 dark:ring-gray-700',
    actionClass: 'border-gray-200 bg-gray-50 text-gray-800 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200',
  },
  missing: {
    label: 'Target not visible',
    Icon: ExclamationTriangleIcon,
    iconClass: 'bg-amber-50 text-amber-700 dark:bg-amber-900/25 dark:text-amber-200',
    panelClass: 'border-amber-200/90 dark:border-amber-800/70',
    accentClass: 'bg-amber-500',
    progressClass: 'bg-amber-500',
    chipClass: 'bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-900/25 dark:text-amber-200 dark:ring-amber-800/70',
    actionClass: 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-800/70 dark:bg-amber-900/20 dark:text-amber-100',
  },
} as const;

function getGuideStepTone(step: GuideStep, targetMissing: boolean): GuideStepTone {
  if (targetMissing) return 'missing';
  if (step.action) return 'action';
  if (step.selector) return 'target';
  return 'context';
}

function getTargetHighlightStyle(rect: DOMRect): CSSProperties {
  const PAD = 6;
  const EDGE_PAD = 8;
  const top = Math.max(EDGE_PAD, rect.top - PAD);
  const left = Math.max(EDGE_PAD, rect.left - PAD);
  const right = Math.min(window.innerWidth - EDGE_PAD, rect.right + PAD);
  const bottom = Math.min(window.innerHeight - EDGE_PAD, rect.bottom + PAD);

  return {
    top,
    left,
    width: Math.max(0, right - left),
    height: Math.max(0, bottom - top),
  };
}

function getPanelStyle(rect: DOMRect | null): CSSProperties | undefined {
  if (!rect) return undefined;
  const PANEL_WIDTH_MAX = 360;
  const PANEL_HEIGHT = 260;
  const GAP = 12;
  const EDGE_PAD = 16;
  const panelWidth = Math.min(PANEL_WIDTH_MAX, window.innerWidth - 32);
  const clampHorizontal = (x: number) =>
    Math.min(Math.max(EDGE_PAD, x), window.innerWidth - panelWidth - EDGE_PAD);
  const clampVertical = (y: number) =>
    Math.min(Math.max(EDGE_PAD, y), window.innerHeight - PANEL_HEIGHT - EDGE_PAD);

  const spaceBelow = window.innerHeight - rect.bottom;
  const spaceAbove = rect.top;
  const spaceRight = window.innerWidth - rect.right;
  const spaceLeft = rect.left;

  // Tall narrow targets (sidebars, vertical nav rails) span most of the
  // viewport height — placing the panel above/below them lands ON the
  // sidebar. Detect that case and prefer horizontal placement.
  const isTallNarrow =
    rect.height > window.innerHeight * 0.5 && rect.width < panelWidth;

  if (isTallNarrow) {
    if (spaceRight >= panelWidth + GAP + EDGE_PAD) {
      return {
        left: rect.right + GAP,
        top: clampVertical(rect.top + Math.min(rect.height / 2 - PANEL_HEIGHT / 2, 32)),
        width: panelWidth,
      };
    }
    if (spaceLeft >= panelWidth + GAP + EDGE_PAD) {
      return {
        left: rect.left - panelWidth - GAP,
        top: clampVertical(rect.top + Math.min(rect.height / 2 - PANEL_HEIGHT / 2, 32)),
        width: panelWidth,
      };
    }
  }

  const horizCenter = rect.left + rect.width / 2 - panelWidth / 2;
  if (spaceBelow >= PANEL_HEIGHT + GAP) {
    return { left: clampHorizontal(horizCenter), top: rect.bottom + GAP, width: panelWidth };
  }
  if (spaceAbove >= PANEL_HEIGHT + GAP) {
    return {
      left: clampHorizontal(horizCenter),
      top: rect.top - PANEL_HEIGHT - GAP,
      width: panelWidth,
    };
  }
  // Last resort: right of target, then left, then center-clamped.
  if (spaceRight >= panelWidth + GAP + EDGE_PAD) {
    return { left: rect.right + GAP, top: clampVertical(rect.top), width: panelWidth };
  }
  if (spaceLeft >= panelWidth + GAP + EDGE_PAD) {
    return { left: rect.left - panelWidth - GAP, top: clampVertical(rect.top), width: panelWidth };
  }
  return {
    left: clampHorizontal(horizCenter),
    top: clampVertical(rect.top - PANEL_HEIGHT - GAP),
    width: panelWidth,
  };
}

export function GuideTourOverlay({
  guide,
  stepIndex,
  onStepChange,
  onClose,
  onComplete,
}: {
  guide: Guide;
  stepIndex: number;
  onStepChange: (index: number) => void;
  onClose: () => void;
  onComplete: () => void;
}) {
  const currentStep = guide.steps[stepIndex] ?? guide.steps[0];
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const [targetMissing, setTargetMissing] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const previousFocusRef = useRef<Element | null>(null);
  const warnedMissingSteps = useRef<Set<string>>(new Set());
  const totalSteps = guide.steps.length;
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === totalSteps - 1;

  useEffect(() => {
    previousFocusRef.current = document.activeElement;
    panelRef.current?.focus();
    return () => {
      const previous = previousFocusRef.current;
      if (previous instanceof HTMLElement) {
        previous.focus();
      }
    };
  }, [guide.id]);

  useEffect(() => {
    if (!currentStep) return undefined;
    let animationFrame = 0;
    const timers: number[] = [];

    const locateTarget = (attempt = 0) => {
      if (!currentStep.selector) {
        setTargetRect(null);
        setTargetMissing(false);
        return;
      }

      const element = document.querySelector<HTMLElement>(currentStep.selector);
      const rect = element?.getBoundingClientRect();
      if (!element || !rect || (rect.width === 0 && rect.height === 0)) {
        setTargetRect(null);
        setTargetMissing(true);
        const warningKey = `${guide.id}:${stepIndex}:${currentStep.selector}`;
        if (import.meta.env.DEV && attempt >= 2 && !warnedMissingSteps.current.has(warningKey)) {
          console.warn(
            `[guides] Missing selector "${currentStep.selector}" for guide "${guide.id}" step ${stepIndex + 1}`,
          );
          warnedMissingSteps.current.add(warningKey);
        }
        return;
      }

      setTargetMissing(false);
      setTargetRect(rect);
      element.scrollIntoView({
        block: 'center',
        inline: 'nearest',
        behavior: prefersReducedMotion() ? 'auto' : 'smooth',
      });
      animationFrame = window.requestAnimationFrame(() => {
        setTargetRect(element.getBoundingClientRect());
      });
    };

    const refreshTarget = () => locateTarget();

    locateTarget();
    timers.push(window.setTimeout(() => locateTarget(1), 140));
    timers.push(window.setTimeout(() => locateTarget(2), 420));
    window.addEventListener('resize', refreshTarget);
    window.addEventListener('scroll', refreshTarget, true);
    return () => {
      window.cancelAnimationFrame(animationFrame);
      timers.forEach((timer) => window.clearTimeout(timer));
      window.removeEventListener('resize', refreshTarget);
      window.removeEventListener('scroll', refreshTarget, true);
    };
  }, [currentStep, guide.id, stepIndex]);

  if (!currentStep) return null;

  const titleId = `guide-${guide.id}-title`;
  const bodyId = `guide-${guide.id}-body`;

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      if (isLast) onComplete();
      else onStepChange(stepIndex + 1);
      return;
    }
    if (event.key === 'ArrowLeft' && !isFirst) {
      event.preventDefault();
      onStepChange(stepIndex - 1);
    }
  };

  const panelStyle = getPanelStyle(targetRect);
  const stepTone = getGuideStepTone(currentStep, targetMissing);
  const stepVisual = STEP_TONE_STYLES[stepTone];
  const StepIcon = stepVisual.Icon;
  const progressPercent = totalSteps > 0 ? ((stepIndex + 1) / totalSteps) * 100 : 0;

  return (
    <div className="fixed inset-0 z-[70] pointer-events-none" aria-live="polite">
      {targetRect && (
        <div
          className="fixed rounded-xl border-2 border-primary-500/90 bg-primary-500/5 shadow-[0_0_0_9999px_rgba(15,23,42,0.18),0_10px_26px_rgba(37,99,235,0.24)] ring-4 ring-primary-500/15 transition-[top,left,width,height] motion-reduce:transition-none dark:bg-primary-500/10"
          style={getTargetHighlightStyle(targetRect)}
          aria-hidden="true"
        >
          <span className="absolute -left-1 -top-1 h-4 w-4 rounded-tl-lg border-l-2 border-t-2 border-primary-300 bg-white dark:bg-gray-950" />
          <span className="absolute -right-1 -top-1 h-4 w-4 rounded-tr-lg border-r-2 border-t-2 border-primary-300 bg-white dark:bg-gray-950" />
          <span className="absolute -bottom-1 -left-1 h-4 w-4 rounded-bl-lg border-b-2 border-l-2 border-primary-300 bg-white dark:bg-gray-950" />
          <span className="absolute -bottom-1 -right-1 h-4 w-4 rounded-br-lg border-b-2 border-r-2 border-primary-300 bg-white dark:bg-gray-950" />
        </div>
      )}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="false"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className={clsx(
          // Slight transparency + backdrop-blur lets users still see the
          // highlighted target peek through, without losing contrast on
          // the panel body text.
          'pointer-events-auto fixed max-h-[calc(100vh-2rem)] overflow-y-auto rounded-lg border bg-white/95 p-3.5 shadow-xl outline-none backdrop-blur-sm dark:bg-gray-900/95',
          'focus-visible:ring-2 focus-visible:ring-primary-500',
          stepVisual.panelClass,
          // ``right-4 bottom-4`` is the no-target fallback only. When an
          // inline ``left+top`` style is set, those Tailwind classes would
          // stretch the panel to fill the full viewport height (browser
          // satisfies BOTH left/right and top/bottom). Keep them off when
          // panelStyle is positioning the panel explicitly.
          panelStyle ? 'w-[360px]' : 'right-4 bottom-4 left-4 sm:left-auto sm:w-[360px]',
        )}
        style={panelStyle}
      >
        <span className={clsx('absolute inset-x-0 top-0 h-1 rounded-t-lg', stepVisual.accentClass)} />
        <div className="flex items-start gap-2.5">
          <span
            className={clsx(
              'mt-0.5 inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg',
              stepVisual.iconClass,
            )}
          >
            <StepIcon className="h-4 w-4" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span
                className={clsx(
                  'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1',
                  stepVisual.chipClass,
                )}
              >
                {stepVisual.label}
              </span>
              <span className="text-[11px] font-medium text-gray-500 dark:text-gray-400">
                {guide.title}
              </span>
            </div>
            <h2 id={titleId} className="mt-0.5 text-sm font-semibold text-gray-900 dark:text-gray-100">
              {currentStep.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:hover:bg-gray-800 dark:hover:text-gray-200"
            aria-label="Close guide"
          >
            <XMarkIcon className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div className="mt-3" aria-label={`${guide.title} step progress`}>
          <div className="flex items-center justify-between text-[11px] font-medium text-gray-500 dark:text-gray-400">
            <span>Step {stepIndex + 1} of {totalSteps}</span>
            <span>{Math.round(progressPercent)}%</span>
          </div>
          <div
            className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800"
            role="progressbar"
            aria-label={`${guide.title} progress`}
            aria-valuemin={1}
            aria-valuemax={totalSteps}
            aria-valuenow={stepIndex + 1}
          >
            <div
              className={clsx(
                'h-full rounded-full transition-[width] duration-200 motion-reduce:transition-none',
                stepVisual.progressClass,
              )}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        <p id={bodyId} className="mt-2 text-sm leading-snug text-gray-700 dark:text-gray-300">
          {currentStep.body}
        </p>
        {currentStep.action && (
          <div
            className={clsx(
              'mt-2 rounded-md border px-2.5 py-2 text-xs leading-snug',
              stepVisual.actionClass,
            )}
          >
            <span className="font-semibold">Try this:</span> {currentStep.action}
          </div>
        )}
        {targetMissing && (
          <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-2 text-xs leading-snug text-amber-900 dark:border-amber-800/70 dark:bg-amber-900/20 dark:text-amber-100">
            <span className="font-semibold">Target not visible.</span> You can keep going; this
            step may appear after the page finishes loading, a filter changes, or your role exposes
            the control.
          </div>
        )}

        <div className="mt-3 flex items-center justify-between gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Skip
          </Button>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onStepChange(stepIndex - 1)}
              disabled={isFirst}
              aria-label="Previous guide step"
            >
              <ChevronLeftIcon className="h-4 w-4" aria-hidden="true" />
            </Button>
            {isLast ? (
              <Button
                size="sm"
                onClick={onComplete}
                leftIcon={<CheckIcon className="h-4 w-4" />}
              >
                Done
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={() => onStepChange(stepIndex + 1)}
                rightIcon={<ChevronRightIcon className="h-4 w-4" />}
              >
                Next
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function GuideFirstRunPrompt({
  role,
  onStart,
  onDismiss,
}: {
  role: GuideRole;
  onStart: () => void;
  onDismiss: () => void;
}) {
  const roleLabel = role.replace('_', ' ');
  return (
    <aside
      aria-label="Guide suggestion"
      className="fixed bottom-4 right-4 z-[60] w-[calc(100vw-2rem)] rounded-lg border border-primary-100 bg-white p-4 shadow-lg dark:border-primary-900/40 dark:bg-gray-900 sm:w-80"
    >
      <div className="flex items-start gap-3">
        <span className="inline-flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-300">
          <AcademicCapIcon className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            New to Link Creative CRM?
          </p>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
            Start with a short {roleLabel} guide. You can skip it and restart from Help anytime.
          </p>
        </div>
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onDismiss}>
          Later
        </Button>
        <Button size="sm" onClick={onStart}>
          Start Tour
        </Button>
      </div>
    </aside>
  );
}

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
    onSuccess: (data) => {
      queryClient.setQueryData(accountKeys.preferences(), data);
      setLocalPref('guideProgress', fromAccountGuideProgress(data.guide_progress));
    },
    onError: (error, variables) => {
      console.warn('[guides] failed to sync guide progress', error);
      if (variables.notifyOnError) {
        showError('Guide progress could not be saved to your account');
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
    if (!isAuthenticated || accountPrefsQuery.isLoading || !accountPrefsQuery.data) {
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
    migratedLocalProgressRef.current = localKey;
    syncGuideProgress({
      progress: progressToMigrate,
      notifyOnError: false,
    });
  }, [
    accountGuideProgress,
    accountPrefsQuery.data,
    accountPrefsQuery.isLoading,
    isAuthenticated,
    localGuideProgress,
    setLocalPref,
    syncGuideProgress,
  ]);

  const updateGuideProgress = useCallback(
    (updater: (prev: GuideProgress | undefined) => GuideProgress) => {
      const next = updater(guideProgress);
      setLocalPref('guideProgress', next);
      if (isAuthenticated) {
        migratedLocalProgressRef.current = guideProgressKey(next);
        syncGuideProgress({
          progress: next,
          notifyOnError: true,
        });
      }
    },
    [guideProgress, isAuthenticated, setLocalPref, syncGuideProgress],
  );

  const startGuide = useCallback(
    (guideId: string) => {
      const guide = getGuideById(guideId);
      if (!guide) return;
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
    startGuide((recommendedUnfinished ?? recommendedGuides[0] ?? availableGuides[0])?.id ?? '');
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

function getPanelStyle(rect: DOMRect | null): CSSProperties | undefined {
  if (!rect) return undefined;
  const panelWidth = Math.min(360, window.innerWidth - 32);
  const left = Math.min(
    Math.max(16, rect.left + rect.width / 2 - panelWidth / 2),
    window.innerWidth - panelWidth - 16,
  );
  const spaceBelow = window.innerHeight - rect.bottom;
  const top = spaceBelow > 240
    ? rect.bottom + 12
    : Math.max(16, rect.top - 232);
  return {
    left,
    top,
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

  return (
    <div className="fixed inset-0 z-[70] pointer-events-none" aria-live="polite">
      {targetRect && (
        <div
          className="fixed rounded-lg border-2 border-primary-500 shadow-[0_0_0_9999px_rgba(15,23,42,0.16),0_0_22px_rgba(59,130,246,0.65)] transition-[top,left,width,height] motion-reduce:transition-none motion-safe:animate-pulse"
          style={{
            top: Math.max(8, targetRect.top - 6),
            left: Math.max(8, targetRect.left - 6),
            width: targetRect.width + 12,
            height: targetRect.height + 12,
          }}
          aria-hidden="true"
        />
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
          'pointer-events-auto fixed right-4 bottom-4 max-h-[calc(100vh-2rem)] overflow-y-auto rounded-lg border border-gray-200 bg-white p-4 shadow-xl outline-none dark:border-gray-700 dark:bg-gray-900',
          'focus-visible:ring-2 focus-visible:ring-primary-500',
          panelStyle ? '' : 'left-4 sm:left-auto sm:w-[360px]',
        )}
        style={panelStyle}
      >
        <div className="flex items-start gap-3">
          <span className="mt-0.5 inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-300">
            <AcademicCapIcon className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              {guide.title} · Step {stepIndex + 1} of {totalSteps}
            </p>
            <h2 id={titleId} className="mt-1 text-base font-semibold text-gray-900 dark:text-gray-100">
              {currentStep.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:hover:bg-gray-800 dark:hover:text-gray-200"
            aria-label="Close guide"
          >
            <XMarkIcon className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <p id={bodyId} className="mt-3 text-sm leading-6 text-gray-700 dark:text-gray-300">
          {currentStep.body}
        </p>
        <div className="mt-3 rounded-md border border-primary-100 bg-primary-50 px-3 py-2 text-sm text-primary-800 dark:border-primary-900/40 dark:bg-primary-900/20 dark:text-primary-200">
          <span className="font-semibold">Try this:</span>{' '}
          {currentStep.action ??
            (currentStep.selector
              ? 'use the highlighted control, then continue when you are ready.'
              : 'read this step, then continue when you are ready.')}
        </div>
        {targetMissing && (
          <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
            This step does not have a visible page target right now, so the guide is showing the instruction without a highlight.
          </p>
        )}

        <div className="mt-4 flex items-center justify-between gap-3">
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

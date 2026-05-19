import {
  AcademicCapIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  NoSymbolIcon,
} from '@heroicons/react/24/outline';
import clsx from 'clsx';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { useGuides } from './GuideProvider';

function getStepSummary(count: number): string {
  return `${count} ${count === 1 ? 'step' : 'steps'}`;
}

export function GuideHelpPanel() {
  const {
    role,
    availableGuides,
    recommendedGuides,
    guidesDisabled,
    isCompleted,
    startGuide,
    setGuidesEnabled,
    resetProgress,
  } = useGuides();
  const totalGuideCount = availableGuides.length;
  const completedCount = availableGuides.filter((guide) => isCompleted(guide.id)).length;
  const completionPercent =
    totalGuideCount > 0 ? Math.round((completedCount / totalGuideCount) * 100) : 0;
  const recommendedIds = new Set(recommendedGuides.map((guide) => guide.id));

  return (
    <Card padding="md" className="border-primary-100 dark:border-primary-900/40" shadow="sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <AcademicCapIcon className="h-5 w-5 text-primary-500" aria-hidden="true" />
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
              Interactive guides
            </h2>
          </div>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
            Role-scoped tours for {role.replace('_', ' ')} users. They highlight the exact controls,
            include short “try this” prompts, and can be restarted whenever you need a refresher.
          </p>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {guidesDisabled ? 'Guides disabled' : 'Guides enabled'} for your account
          </p>
        </div>
        <div className="w-full lg:w-80">
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-900/40">
            <div className="flex items-center justify-between gap-3 text-xs font-medium text-gray-600 dark:text-gray-300">
              <span>Guide progress</span>
              <span>
                {completedCount}/{totalGuideCount} complete
              </span>
            </div>
            <div
              className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700"
              role="progressbar"
              aria-label="Guide completion progress"
              aria-valuemin={0}
              aria-valuemax={totalGuideCount}
              aria-valuenow={completedCount}
            >
              <div
                className="h-full rounded-full bg-primary-500 transition-[width] duration-200 motion-reduce:transition-none"
                style={{ width: `${completionPercent}%` }}
              />
            </div>
          </div>
          <div className="mt-2 flex flex-wrap justify-end gap-2">
            <Button
              variant={guidesDisabled ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => setGuidesEnabled(guidesDisabled)}
              leftIcon={guidesDisabled ? <AcademicCapIcon className="h-4 w-4" /> : <NoSymbolIcon className="h-4 w-4" />}
            >
              {guidesDisabled ? 'Re-enable guides' : 'Disable guides'}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={resetProgress}
              leftIcon={<ArrowPathIcon className="h-4 w-4" />}
            >
              Reset progress
            </Button>
          </div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {availableGuides.map((guide) => {
          const completed = isCompleted(guide.id);
          const recommended = recommendedIds.has(guide.id);
          return (
            <div
              key={guide.id}
              className={clsx(
                'rounded-lg border bg-white p-3 shadow-sm transition-colors dark:bg-gray-900/40',
                completed
                  ? 'border-green-200 dark:border-green-900/60'
                  : recommended
                    ? 'border-primary-200 dark:border-primary-800/70'
                    : 'border-gray-200 dark:border-gray-700',
              )}
            >
              <div
                className={clsx(
                  'mb-3 h-1 rounded-full',
                  completed ? 'bg-green-500' : recommended ? 'bg-primary-500' : 'bg-gray-300 dark:bg-gray-600',
                )}
              />
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {guide.title}
                    </h3>
                    {recommended && (
                      <span className="rounded-full bg-primary-100 px-2 py-0.5 text-[11px] font-medium text-primary-700 dark:bg-primary-900/30 dark:text-primary-200">
                        Recommended
                      </span>
                    )}
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                      {getStepSummary(guide.steps.length)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-5 text-gray-600 dark:text-gray-300">
                    {guide.description}
                  </p>
                </div>
                {completed && (
                  <CheckCircleIcon className="h-5 w-5 flex-shrink-0 text-green-500" aria-label="Completed" />
                )}
              </div>
              <Button
                size="sm"
                variant={completed ? 'secondary' : 'primary'}
                className="mt-3 w-full"
                onClick={() => startGuide(guide.id)}
              >
                {completed ? 'Restart tour' : 'Start tour'}
              </Button>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

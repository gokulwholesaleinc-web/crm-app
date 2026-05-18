import {
  AcademicCapIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  NoSymbolIcon,
} from '@heroicons/react/24/outline';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { useGuides } from './GuideProvider';

export function GuideHelpPanel() {
  const {
    role,
    availableGuides,
    recommendedGuides,
    completedGuideIds,
    guidesDisabled,
    isCompleted,
    startGuide,
    setGuidesEnabled,
    resetProgress,
  } = useGuides();
  const completedCount = completedGuideIds.length;
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
            {completedCount} completed · {guidesDisabled ? 'Guides disabled' : 'Guides enabled'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
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

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {availableGuides.map((guide) => {
          const completed = isCompleted(guide.id);
          return (
            <div
              key={guide.id}
              className="rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800/60"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {guide.title}
                    </h3>
                    {recommendedIds.has(guide.id) && (
                      <span className="rounded-full bg-primary-100 px-2 py-0.5 text-[11px] font-medium text-primary-700 dark:bg-primary-900/30 dark:text-primary-200">
                        Recommended
                      </span>
                    )}
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

import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Spinner } from '../../components/ui/Spinner';
import {
  useCacheStats,
  useClearAllCache,
  useClearCachePattern,
} from '../../hooks/useAdmin';

const numberFormatter = new Intl.NumberFormat(undefined);

const CACHE_PATTERNS = [
  { label: 'Dashboard Cache', pattern: 'dashboard*' },
  { label: 'Settings Cache', pattern: 'tenant_settings*' },
  { label: 'Roles Cache', pattern: 'roles*' },
  { label: 'Pipeline Stages', pattern: 'pipeline_stages*' },
  { label: 'Lead Sources', pattern: 'lead_sources*' },
  { label: 'Admin Stats', pattern: 'admin_stats*' },
] as const;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface StatItemProps {
  label: string;
  value: string;
}

function StatItem({ label, value }: StatItemProps) {
  return (
    <div className="flex flex-col items-center p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
      <span className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</span>
      <span
        className="text-lg font-semibold text-gray-900 dark:text-gray-100"
        style={{ fontVariantNumeric: 'tabular-nums' }}
      >
        {value}
      </span>
    </div>
  );
}

export default function CacheManagement() {
  const { data: stats, isLoading } = useCacheStats();
  const clearAll = useClearAllCache();
  const clearPattern = useClearCachePattern();

  return (
    <Card>
      <CardHeader
        title="Cache Management"
        description="Monitor and manage the server-side in-memory cache"
      />
      <CardBody>
        {isLoading ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : !stats ? (
          <p className="text-sm text-gray-500 dark:text-gray-400 py-4">
            Unable to load cache stats
          </p>
        ) : (
          <div className="space-y-6">
            {/* Stats Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <StatItem label="Active Keys" value={numberFormatter.format(stats.active_keys)} />
              <StatItem label="Expired Keys" value={numberFormatter.format(stats.expired_keys)} />
              <StatItem label="Memory" value={formatBytes(stats.memory_bytes)} />
              <StatItem label="Hit Rate" value={`${stats.hit_rate_percent}%`} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <StatItem label="Cache Hits" value={numberFormatter.format(stats.hits)} />
              <StatItem label="Cache Misses" value={numberFormatter.format(stats.misses)} />
            </div>

            {/* Actions */}
            <div className="space-y-3">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Clear Cache
              </h3>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => clearAll.mutate()}
                  disabled={clearAll.isPending}
                  aria-label="Clear all cache entries"
                  className="inline-flex items-center px-3 py-1.5 text-sm font-medium rounded-md bg-red-600 text-white hover:bg-red-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600 disabled:opacity-50 transition-colors"
                >
                  {clearAll.isPending ? 'Clearing...' : 'Clear All Cache'}
                </button>
                {CACHE_PATTERNS.map((item) => (
                  <button
                    key={item.pattern}
                    type="button"
                    onClick={() => clearPattern.mutate(item.pattern)}
                    disabled={clearPattern.isPending}
                    aria-label={`Clear ${item.label.toLowerCase()}`}
                    className="inline-flex items-center px-3 py-1.5 text-sm font-medium rounded-md bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:opacity-50 transition-colors"
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              {clearAll.isSuccess ? (
                <p className="text-sm text-green-600 dark:text-green-400" aria-live="polite">
                  {clearAll.data.message}
                </p>
              ) : null}
              {clearPattern.isSuccess ? (
                <p className="text-sm text-green-600 dark:text-green-400" aria-live="polite">
                  {clearPattern.data.message}
                </p>
              ) : null}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

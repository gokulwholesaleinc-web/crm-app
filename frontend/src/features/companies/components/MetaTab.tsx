import { useState } from 'react';
import { Button, Spinner } from '../../../components/ui';
import { useCompanyMeta, useSyncCompanyMeta, useExportMetaCsv } from '../../../hooks/useMeta';
import { formatDate } from '../../../utils/formatters';

interface MetaTabProps {
  companyId: number;
}

export default function MetaTab({ companyId }: MetaTabProps) {
  const { data: meta, isLoading, error } = useCompanyMeta(companyId);
  const syncMutation = useSyncCompanyMeta();
  const exportMutation = useExportMetaCsv();
  const [pageId, setPageId] = useState('');

  const handleSync = () => {
    if (!pageId.trim()) return;
    syncMutation.mutate({ companyId, pageId: pageId.trim() });
  };

  const handleExport = () => {
    exportMutation.mutate(companyId);
  };

  return (
    <div className="space-y-6">
      {/* Sync Form */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border dark:border-gray-700 p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Sync Meta Page</h3>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <label htmlFor="meta-page-id" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Facebook Page ID
            </label>
            <input
              id="meta-page-id"
              type="text"
              value={pageId}
              onChange={(e) => setPageId(e.target.value)}
              placeholder="Enter page ID..."
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 dark:placeholder-gray-400 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              spellCheck={false}
            />
          </div>
          <Button
            onClick={handleSync}
            disabled={!pageId.trim() || syncMutation.isPending}
            className="w-full sm:w-auto"
          >
            {syncMutation.isPending ? 'Syncing...' : 'Sync'}
          </Button>
        </div>
        {syncMutation.isError && (
          <p className="mt-2 text-sm text-red-600" aria-live="polite">
            Failed to sync Meta data. Please try again.
          </p>
        )}
        {syncMutation.isSuccess && (
          <p className="mt-2 text-sm text-green-600" aria-live="polite">
            Meta data synced successfully.
          </p>
        )}
      </div>

      {/* Meta Data Display */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Spinner />
        </div>
      ) : error ? (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border dark:border-gray-700 p-6 text-center">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No Meta data found for this company. Use the sync form above to connect a Facebook page.
          </p>
        </div>
      ) : meta ? (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border dark:border-gray-700 p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Page Data</h3>
            <Button variant="secondary" size="sm" onClick={handleExport} disabled={exportMutation.isPending}>
              {exportMutation.isPending ? 'Exporting...' : 'Export CSV'}
            </Button>
          </div>

          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {meta.page_name && (
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Page Name</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{meta.page_name}</dd>
              </div>
            )}
            {meta.page_id && (
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Page ID</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{meta.page_id}</dd>
              </div>
            )}
            {meta.category && (
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Category</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{meta.category}</dd>
              </div>
            )}
            {meta.followers_count != null && (
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Followers</dt>
                <dd className="mt-1 text-sm text-gray-900" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {meta.followers_count.toLocaleString()}
                </dd>
              </div>
            )}
            {meta.likes_count != null && (
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Likes</dt>
                <dd className="mt-1 text-sm text-gray-900" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {meta.likes_count.toLocaleString()}
                </dd>
              </div>
            )}
            {meta.website && (
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Website</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                  <a
                    href={meta.website}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary-600 hover:text-primary-800"
                  >
                    {meta.website}
                  </a>
                </dd>
              </div>
            )}
            {meta.about && (
              <div className="sm:col-span-2">
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">About</dt>
                <dd className="mt-1 text-sm text-gray-900 whitespace-pre-wrap">{meta.about}</dd>
              </div>
            )}
            {meta.last_synced_at && (
              <div>
                <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Last Synced</dt>
                <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{formatDate(meta.last_synced_at, 'long')}</dd>
              </div>
            )}
          </dl>
        </div>
      ) : null}
    </div>
  );
}

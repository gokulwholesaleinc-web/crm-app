import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export const STALE_CHUNK_RELOAD_FLAG = 'crm:stale-chunk-reload-attempted';

export function isStaleChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const message = error.message.toLowerCase();
  // The four named conditions below cover Vite, webpack, and Safari for
  // dynamic-import failures. We deliberately do NOT match a generic
  // "/assets/ + 404" pair — an API 404 against any path containing
  // "/assets/" (e.g. /api/v1/assets/123) would be misclassified as a
  // stale chunk and silently reload the page.
  return (
    error.name === 'ChunkLoadError' ||
    message.includes('failed to fetch dynamically imported module') ||
    message.includes('error loading dynamically imported module') ||
    message.includes('importing a module script failed')
  );
}

function trySessionStorage(action: (storage: Storage) => void): void {
  try {
    action(window.sessionStorage);
  } catch {
    // Private browsing / storage-denied environments should still render
    // the normal error boundary fallback.
  }
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  private clearStaleChunkFlagTimer: number | undefined;

  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidMount() {
    this.clearStaleChunkFlagTimer = window.setTimeout(() => {
      if (!this.state.hasError) {
        trySessionStorage((storage) => storage.removeItem(STALE_CHUNK_RELOAD_FLAG));
      }
    }, 5000);
  }

  componentWillUnmount() {
    if (this.clearStaleChunkFlagTimer !== undefined) {
      window.clearTimeout(this.clearStaleChunkFlagTimer);
    }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    if (!isStaleChunkLoadError(error)) {
      return;
    }

    let shouldReload = true;
    trySessionStorage((storage) => {
      shouldReload = storage.getItem(STALE_CHUNK_RELOAD_FLAG) !== '1';
      if (shouldReload) storage.setItem(STALE_CHUNK_RELOAD_FLAG, '1');
    });

    if (shouldReload) {
      window.location.reload();
    }
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const staleChunk = isStaleChunkLoadError(this.state.error);

      return (
        <div className="flex min-h-[400px] items-center justify-center p-6">
          <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-8 text-center shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
              <svg
                className="h-6 w-6 text-red-600 dark:text-red-400"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
                />
              </svg>
            </div>
            <h2 className="mb-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
              {staleChunk ? 'App update needed' : 'Something went wrong'}
            </h2>
            <p className="mb-6 text-sm text-gray-500 dark:text-gray-400">
              {staleChunk
                ? 'A new version was deployed while this page was open. Reload to get the latest files.'
                : 'An unexpected error occurred. You can try again or reload the page.'}
            </p>
            <div className="flex items-center justify-center gap-3">
              <button
                type="button"
                onClick={this.handleRetry}
                className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
              >
                Try again
              </button>
              <button
                type="button"
                onClick={this.handleReload}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
              >
                Reload page
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

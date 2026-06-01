import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { CheckIcon } from '@heroicons/react/24/outline';
import { useForceLightMode } from '../../hooks/useForceLightMode';
import { setPublicPageMeta } from '../proposals/publicMeta';
import type { OnboardingDownloadDocument } from '../../types';

// Bare axios — the recipient clicking the e-mailed link is NOT logged in. The
// download token in the URL gates the backend landing endpoint; no CRM auth,
// no cookies, no tenant header (mirrors the public onboarding view).
const publicClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

const apiBase = import.meta.env.VITE_API_URL || '';
const resolveUrl = (url: string) => (/^https?:\/\//i.test(url) ? url : `${apiBase}${url}`);

/**
 * Landing page for the e-mailed ``/onboarding/complete/:token`` link. The
 * completion notice points the recipient here; we resolve the download token
 * against the backend landing endpoint and render one link per signed PDF.
 * A 404 means the link is expired/revoked (download tokens live 7 days).
 */
function OnboardingDownloadLanding() {
  const { token } = useParams<{ token: string }>();
  const [docs, setDocs] = useState<OnboardingDownloadDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useForceLightMode();

  useEffect(() => {
    const restoreMeta = setPublicPageMeta({
      title: 'Your onboarding documents',
      description: 'Download your completed onboarding documents.',
      type: 'website',
    });
    return restoreMeta;
  }, []);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await publicClient.get<{ documents: OnboardingDownloadDocument[] }>(
          `/api/onboarding/download/${token}`,
        );
        if (!cancelled) setDocs(res.data.documents ?? []);
      } catch (err) {
        if (cancelled) return;
        const status = (err as { response?: { status?: number } }).response?.status;
        setError(
          status === 404
            ? 'This download link is no longer available — it may have expired. Please contact us for a new copy.'
            : 'We could not load your documents right now. Please try again in a moment.',
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div role="status" aria-label="Loading your documents…" className="text-center animate-pulse motion-reduce:animate-none">
          <div className="h-7 w-48 bg-gray-200 rounded mx-auto mb-3" />
          <div className="h-3 w-28 bg-gray-200 rounded mx-auto" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center px-6">
        <div className="text-center max-w-md">
          <h1 className="text-2xl font-semibold text-gray-900 mb-2">Link unavailable</h1>
          <p className="text-sm text-gray-500 leading-relaxed">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 antialiased">
      <main className="mx-auto max-w-md px-6 py-14">
        <section className="text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
            <CheckIcon className="h-6 w-6 text-green-700" aria-hidden="true" />
          </div>
          <h1 className="mt-4 text-2xl font-semibold tracking-tight">Your onboarding documents</h1>
          <p className="mt-2 text-sm text-gray-600 leading-relaxed text-pretty">
            Download your completed, signed documents below.
          </p>

          {docs.length > 0 ? (
            <div className="mt-8 text-left space-y-2">
              {docs.map((d) => (
                <a
                  key={d.doc_id}
                  href={resolveUrl(d.url)}
                  target="_blank"
                  rel="noreferrer"
                  referrerPolicy="no-referrer"
                  className="flex items-center justify-between gap-3 rounded border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-900 shadow-sm hover:border-gray-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green-600"
                >
                  <span className="truncate">{d.title}</span>
                  <span className="text-xs font-semibold text-green-700">Download</span>
                </a>
              ))}
            </div>
          ) : (
            <p className="mt-6 text-sm text-gray-500">
              No documents are available for this link.
            </p>
          )}
        </section>
      </main>
    </div>
  );
}

export default OnboardingDownloadLanding;

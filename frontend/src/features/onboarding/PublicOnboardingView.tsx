import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useParams } from 'react-router-dom';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  ArrowPathIcon,
  CheckIcon,
  PencilSquareIcon,
} from '@heroicons/react/24/outline';
import axios, { type AxiosInstance } from 'axios';
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist';
import type { PDFDocumentProxy } from 'pdfjs-dist';
// pdf.js v4 ships an .mjs worker; Vite's ``?url`` asset-pipelines it next to
// the bundle so the worker stays version-locked to the installed pdfjs-dist —
// same setup as the proposals SignatureFieldPicker / onboarding editor.
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { sanitizeHexColor, withAlpha } from '../../utils/colorValidation';
import { useForceLightMode } from '../../hooks/useForceLightMode';
import { setPublicPageMeta } from '../proposals/publicMeta';
import {
  RENDER_SCALE,
  pdfCoordsToBox,
  clamp,
  type DrawnBox,
} from '../../lib/pdfCoords';
import { SignatureCanvas, type SignatureCanvasHandle } from '../../components/SignatureCanvas';
import type {
  OnboardingPublicPacket,
  OnboardingPublicBranding,
  OnboardingPublicDocument,
  OnboardingDownloadDocument,
  OnboardingFieldDefinition,
} from '../../types';

GlobalWorkerOptions.workerSrc = pdfWorker;

// Bare axios instance for the public (unauthenticated) onboarding endpoints.
// Deliberately does NOT attach the CRM Bearer token or X-Tenant-Slug header,
// and carries NO cookies — the client clicking an onboarding link isn't
// logged in. The session token returned by /verify is attached per-request
// in the ``X-Onboarding-Session`` header (set via setSessionToken below) so a
// 401 here never wipes a CRM staff user's own session if they preview a link.
const publicClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

// Translate a raw axios error from the public client into a client-readable
// message. Status-branched so a transient 502 reads as "try again" rather than
// the same generic notice we surface when the server explicitly rejects. Duck
// typing instead of ``axios.isAxiosError`` so it works under module mocks.
function publicErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object') {
    const e = err as {
      response?: { status?: number; data?: { detail?: unknown } };
      code?: string;
      isAxiosError?: boolean;
    };
    const detail = e.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail.trim();
    if (Array.isArray(detail) && detail.length > 0) {
      const msgs = detail
        .map((d) => (d && typeof d === 'object' && 'msg' in d ? (d as { msg?: unknown }).msg : null))
        .filter((m): m is string => typeof m === 'string' && m.trim() !== '');
      if (msgs.length > 0) return msgs.join('; ');
    }
    if (e.code === 'ECONNABORTED') {
      return 'The request timed out. Please check your connection and try again.';
    }
    if ('response' in e || e.isAxiosError) {
      const status = e.response?.status;
      if (!status) return 'Network error — please check your connection and try again.';
      if (status >= 500) return 'Our server hit a temporary error. Please try again in a moment.';
    }
  }
  console.error('public onboarding action failed', err);
  return fallback;
}

/** The HTTP status of an axios error, or null when there's no response. */
function errorStatus(err: unknown): number | null {
  if (err && typeof err === 'object') {
    const status = (err as { response?: { status?: number } }).response?.status;
    if (typeof status === 'number') return status;
  }
  return null;
}

const DEFAULT_BRANDING: OnboardingPublicBranding = {
  company_name: null,
  logo_url: null,
  primary_color: '#6366f1',
  secondary_color: '#8b5cf6',
  accent_color: '#22c55e',
  bg_color_light: '#f9fafb',
  surface_color_light: '#ffffff',
  footer_text: null,
  privacy_policy_url: null,
  terms_of_service_url: null,
};

// Shown only if the API response predates the server-authored disclosure
// (e.g. a stale cache during the deploy window). The live disclosure always
// comes from the server so the on-screen text stays byte-identical to the
// per-document snapshot persisted at completion.
const FALLBACK_ESIGN_DISCLOSURE =
  'By drawing and submitting your signature, you agree that it constitutes ' +
  'your legally binding electronic signature under the US ESIGN Act ' +
  '(15 USC §7001) and applicable state UETA statutes, with the same legal ' +
  'effect as a handwritten signature.\n\nWe record your name, email address, ' +
  'IP address, browser user-agent, and timestamp at submission. This audit ' +
  'trail is retained alongside your documents for dispute resolution.';

// Status values whose documents can still be filled + submitted (note §2).
const WRITABLE_STATUSES = new Set(['active', 'opened', 'in_progress']);
// Terminal-dead statuses the server answers with 410 — the link is gone.
const DEAD_STATUSES = new Set(['abandoned', 'expired', 'revoked']);

function PublicOnboardingView() {
  const { token } = useParams<{ token: string }>();

  const [packet, setPacket] = useState<OnboardingPublicPacket | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [logoError, setLogoError] = useState(false);

  // Bearer session token returned by /verify, held in memory only (no cookie,
  // no localStorage) and attached to every subsequent request.
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const sessionTokenRef = useRef<string | null>(null);
  sessionTokenRef.current = sessionToken;

  // Email-gate state.
  const [email, setEmail] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  // Step-through state — one document at a time.
  const [docIndex, setDocIndex] = useState(0);
  // Local draft of field values per document (id -> string), seeded from the
  // server payload and the source of truth for the inputs.
  const [draftValues, setDraftValues] = useState<Record<number, Record<string, string>>>({});
  // Per-document version captured for the optimistic-lock PATCH ``base_version``.
  const [docVersions, setDocVersions] = useState<Record<number, number>>({});
  // Which documents the client has stepped to / saved (every-doc-viewed gate).
  const [viewedDocIds, setViewedDocIds] = useState<Set<number>>(() => new Set());
  const [savingDoc, setSavingDoc] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);

  // Signature drawn once, reused across all documents. Typed non-null so the
  // ref is assignable to the forwardRef ``ref`` prop (the imperative handle is
  // populated by SignatureCanvas; we still guard with optional chaining).
  const sigRef = useRef<SignatureCanvasHandle>(null);
  const [sigEmpty, setSigEmpty] = useState(true);
  const [signatureVersion, setSignatureVersion] = useState<number>(0);
  const [signatureSaved, setSignatureSaved] = useState(false);
  const [savingSig, setSavingSig] = useState(false);
  const [sigError, setSigError] = useState<string | null>(null);

  // Submit / success state.
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  // The in-session download landing URL returned by /complete (carries the raw
  // download token — the recipient's one in-session chance to fetch the signed
  // PDFs before the page reloads; the e-mailed link is the durable fallback).
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);

  useForceLightMode();

  const requestHeaders = useCallback(() => {
    const t = sessionTokenRef.current;
    return t ? { 'X-Onboarding-Session': t } : undefined;
  }, []);

  // --- Initial load (pre-gate) -------------------------------------------
  const fetchPacket = useCallback(async () => {
    if (!token) return;
    try {
      const res = await publicClient.get<OnboardingPublicPacket>(
        `/api/onboarding/public/${token}`,
        { headers: requestHeaders() },
      );
      setPacket(res.data);
      setLoadError(null);
      if (res.data.status === 'completed') setCompleted(true);
    } catch (err) {
      const status = errorStatus(err);
      // 410 = the link is no longer available (abandoned/expired/revoked).
      if (status === 410) {
        setLoadError('This onboarding link is no longer available. Please contact us for a new link.');
      } else if (status === 404) {
        setLoadError('Onboarding link not found. Please check the link or contact us.');
      } else {
        setLoadError(publicErrorMessage(err, 'This onboarding link is not available right now. Please try again later.'));
      }
    } finally {
      setLoading(false);
    }
  }, [token, requestHeaders]);

  useEffect(() => {
    void fetchPacket();
  }, [fetchPacket]);

  useEffect(() => {
    setLogoError(false);
  }, [packet?.branding?.logo_url]);

  // Seed local draft + version state whenever the post-gate documents arrive.
  // ``field_values`` from the server is authoritative on (re)load; the local
  // draft only diverges between saves.
  const documents = packet?.documents;
  useEffect(() => {
    if (!documents) return;
    setDraftValues((prev) => {
      const next = { ...prev };
      for (const doc of documents) {
        if (next[doc.id] === undefined) next[doc.id] = { ...doc.field_values };
      }
      return next;
    });
    setDocVersions((prev) => {
      const next = { ...prev };
      for (const doc of documents) next[doc.id] = doc.field_values_version;
      return next;
    });
    if (packet?.signature_version !== undefined) {
      setSignatureVersion(packet.signature_version);
    }
    if (packet?.has_signature) setSignatureSaved(true);
  }, [documents, packet?.signature_version, packet?.has_signature]);

  const brandingCompanyName = packet?.branding?.company_name;
  useEffect(() => {
    if (!brandingCompanyName && !packet) return;
    const company = brandingCompanyName ?? 'Onboarding';
    const title = `Onboarding — ${company}`;
    const previous = document.title;
    document.title = title;
    // NB: NO token in the canonical URL / OG tags (note §8) — the public link
    // carries a high-entropy token we must never surface to crawlers/unfurls.
    const restoreMeta = setPublicPageMeta({
      title,
      description: `Complete your onboarding documents for ${company}.`,
      type: 'website',
    });
    return () => {
      document.title = previous;
      restoreMeta();
    };
  }, [brandingCompanyName, packet]);

  const branding = useMemo(() => {
    const raw = packet?.branding ?? DEFAULT_BRANDING;
    return {
      ...raw,
      primary_color: sanitizeHexColor(raw.primary_color, DEFAULT_BRANDING.primary_color),
      secondary_color: sanitizeHexColor(raw.secondary_color, DEFAULT_BRANDING.secondary_color),
      accent_color: sanitizeHexColor(raw.accent_color, DEFAULT_BRANDING.accent_color),
      bg_color_light: sanitizeHexColor(raw.bg_color_light, DEFAULT_BRANDING.bg_color_light),
      surface_color_light: sanitizeHexColor(raw.surface_color_light, DEFAULT_BRANDING.surface_color_light),
    };
  }, [packet?.branding]);

  // --- Email-gate verify -------------------------------------------------
  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || verifying) return;
    const trimmed = email.trim();
    if (!trimmed) {
      setVerifyError('Please enter your email address.');
      return;
    }
    setVerifying(true);
    setVerifyError(null);
    try {
      const res = await publicClient.post<{
        success: boolean;
        session_token: string | null;
        expires_in?: number;
      }>(`/api/onboarding/public/${token}/verify`, { email: trimmed });
      // The backend answers a WRONG e-mail with HTTP 200 + success:false (no
      // enumeration), so a 200 alone is not success — gate on the flag, else
      // the user is silently dropped back on the same form with no feedback.
      if (!res.data.success || !res.data.session_token) {
        setVerifyError(
          'We could not verify that email for this link. Please check it and try again.',
        );
        return;
      }
      const newToken = res.data.session_token;
      sessionTokenRef.current = newToken;
      setSessionToken(newToken);
      // Re-fetch with the session attached to pull the post-gate documents.
      await fetchPacket();
    } catch (err) {
      const status = errorStatus(err);
      if (status === 429) {
        setVerifyError('Too many attempts. Please wait a few minutes and try again.');
      } else if (status === 410) {
        setLoadError('This onboarding link is no longer available. Please contact us for a new link.');
      } else {
        // Generic on 401/403 — the server never confirms whether the email
        // matched (no enumeration). Surface a single, non-revealing notice.
        setVerifyError(
          publicErrorMessage(
            err,
            'We could not verify that email for this link. Please check it and try again.',
          ),
        );
      }
    } finally {
      setVerifying(false);
    }
  };

  // --- Per-document save (PATCH) -----------------------------------------
  // Memoized so the array reference is stable across renders that don't change
  // the documents — the validation/gating useMemos below depend on it.
  const docs = useMemo(() => packet?.documents ?? [], [packet?.documents]);
  const currentDoc = docs[docIndex] ?? null;

  // Mark the current document viewed once it's shown post-gate.
  const currentDocId = currentDoc?.id ?? null;
  useEffect(() => {
    if (currentDocId == null) return;
    setViewedDocIds((curr) => {
      if (curr.has(currentDocId)) return curr;
      const next = new Set(curr);
      next.add(currentDocId);
      return next;
    });
  }, [currentDocId]);

  const setFieldValue = useCallback((docId: number, fieldId: string, value: string) => {
    setDraftValues((curr) => ({
      ...curr,
      [docId]: { ...(curr[docId] ?? {}), [fieldId]: value },
    }));
  }, []);

  const saveDocument = useCallback(
    async (doc: OnboardingPublicDocument): Promise<boolean> => {
      if (!token) return false;
      setSavingDoc(true);
      setDocError(null);
      try {
        const res = await publicClient.patch<{ field_values_version: number }>(
          `/api/onboarding/public/${token}/documents/${doc.id}`,
          {
            field_values: draftValues[doc.id] ?? {},
            base_version: docVersions[doc.id] ?? doc.field_values_version,
          },
          { headers: requestHeaders() },
        );
        setDocVersions((curr) => ({ ...curr, [doc.id]: res.data.field_values_version }));
        return true;
      } catch (err) {
        const status = errorStatus(err);
        if (status === 409) {
          // Lost update (version drifted) OR the packet moved to a non-writable
          // state. Re-fetch so the inputs reconcile to the server's values.
          setDocError('Your form was updated elsewhere. We refreshed it — please review and continue.');
          await fetchPacket();
        } else if (status === 410) {
          setLoadError('This onboarding link is no longer available. Please contact us for a new link.');
        } else {
          setDocError(publicErrorMessage(err, 'We could not save this document. Please try again.'));
        }
        return false;
      } finally {
        setSavingDoc(false);
      }
    },
    [token, draftValues, docVersions, requestHeaders, fetchPacket],
  );

  // --- Signature save (POST) ---------------------------------------------
  const saveSignature = useCallback(async (): Promise<boolean> => {
    if (!token) return false;
    const dataUrl = sigRef.current?.toDataURL() ?? null;
    if (!dataUrl) {
      setSigError('Please draw your signature first.');
      return false;
    }
    setSavingSig(true);
    setSigError(null);
    try {
      const res = await publicClient.post<{ signature_version: number }>(
        `/api/onboarding/public/${token}/signature`,
        {
          signature_png_base64: dataUrl,
          base_signature_version: signatureVersion,
        },
        { headers: requestHeaders() },
      );
      setSignatureVersion(res.data.signature_version);
      setSignatureSaved(true);
      return true;
    } catch (err) {
      const status = errorStatus(err);
      if (status === 409) {
        setSigError('Your signature was updated elsewhere. Please redraw and save again.');
        await fetchPacket();
      } else if (status === 410) {
        setLoadError('This onboarding link is no longer available. Please contact us for a new link.');
      } else {
        setSigError(publicErrorMessage(err, 'We could not save your signature. Please try again.'));
      }
      return false;
    } finally {
      setSavingSig(false);
    }
  }, [token, signatureVersion, requestHeaders, fetchPacket]);

  // --- Submit (POST /complete) + completion poll -------------------------
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!token || submitting) return;
    // Save the open document first so its latest values are persisted before
    // the server validates completion.
    if (currentDoc && !(await saveDocument(currentDoc))) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await publicClient.post<{
        status: string;
        download_url?: string | null;
      }>(`/api/onboarding/public/${token}/complete`, {}, { headers: requestHeaders() });
      // Capture the in-session download landing URL so the success screen can
      // render the signed-PDF links (this is the only place the raw download
      // token is exposed — a later refetch never carries it).
      if (res.data.download_url) setDownloadUrl(res.data.download_url);
      if (res.data.status === 'completing') {
        // Server is stamping in the background — re-fetch the public payload.
        // The status-watch effect below keeps polling until it flips to
        // ``completed``.
        await fetchPacket();
      } else {
        await fetchPacket();
        setCompleted(true);
      }
    } catch (err) {
      const status = errorStatus(err);
      if (status === 409) {
        // Already in progress / already completed, or a claim race.
        setSubmitError('This packet is already being finalized. Refreshing…');
        await fetchPacket();
      } else if (status === 422) {
        setSubmitError(publicErrorMessage(err, 'Some required fields are missing or invalid. Please review every document.'));
      } else if (status === 410) {
        setLoadError('This onboarding link is no longer available. Please contact us for a new link.');
      } else {
        setSubmitError(publicErrorMessage(err, 'We could not submit your documents. Please try again.'));
      }
    } finally {
      setSubmitting(false);
    }
  }, [token, submitting, currentDoc, saveDocument, requestHeaders, fetchPacket]);

  // When a background ``completing`` poll lands on ``completed``, stop polling
  // and show the success screen with downloads.
  useEffect(() => {
    if (packet?.status === 'completed') {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      setCompleted(true);
    } else if (packet?.status === 'completing' && sessionToken && !completed) {
      // Keep polling while the server finalizes.
      if (!pollTimerRef.current) {
        pollTimerRef.current = setTimeout(() => {
          pollTimerRef.current = null;
          void fetchPacket();
        }, 2000);
      }
    }
  }, [packet?.status, sessionToken, completed, fetchPacket]);

  // --- Derived gating ----------------------------------------------------
  // A signature is required when any doc is e-sign OR carries a signature field
  // — matching the backend completion gate (which demands a signature whenever
  // a signature field exists). The two are kept consistent at packet creation,
  // but aligning the predicates keeps the pad from ever hiding on a doc the
  // server will then refuse to complete without a signature.
  const requiresSignature = useMemo(
    () =>
      docs.some(
        (d) =>
          d.requires_esign ||
          d.field_definitions.some((f) => f.kind === 'signature'),
      ),
    [docs],
  );

  const allDocsViewed = docs.length > 0 && docs.every((d) => viewedDocIds.has(d.id));

  const missingRequired = useMemo(() => {
    const missing: string[] = [];
    for (const doc of docs) {
      const values = draftValues[doc.id] ?? doc.field_values;
      for (const f of doc.field_definitions) {
        if (f.kind === 'signature') continue; // covered by the drawn signature
        if (f.required && !(values[f.id] ?? '').trim()) {
          missing.push(`${doc.original_filename}: ${f.label}`);
        }
      }
    }
    return missing;
  }, [docs, draftValues]);

  const canSubmit =
    allDocsViewed &&
    missingRequired.length === 0 &&
    (!requiresSignature || signatureSaved) &&
    !submitting;

  const goPrevDoc = async () => {
    if (currentDoc) await saveDocument(currentDoc);
    setDocIndex((i) => Math.max(0, i - 1));
  };
  const goNextDoc = async () => {
    if (currentDoc && !(await saveDocument(currentDoc))) return;
    setDocIndex((i) => Math.min(docs.length - 1, i + 1));
  };

  // --- Render ------------------------------------------------------------
  const companyDisplayName = branding.company_name || 'Onboarding';
  const primary = branding.primary_color;
  const accent = branding.accent_color;

  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div role="status" aria-label="Loading onboarding…" className="animate-pulse motion-reduce:animate-none text-center">
          <div className="h-7 w-40 bg-gray-200 rounded mx-auto mb-3" />
          <div className="h-3 w-24 bg-gray-200 rounded mx-auto" />
        </div>
      </div>
    );
  }

  if (loadError || !packet) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center px-6">
        <div className="text-center max-w-md">
          <h1 className="text-2xl font-semibold text-gray-900 mb-2">Link unavailable</h1>
          <p className="text-sm text-gray-500 leading-relaxed">
            {loadError || 'This onboarding link is no longer valid. Please contact us for a new link.'}
          </p>
        </div>
      </div>
    );
  }

  const pageStyle = { backgroundColor: branding.bg_color_light };
  const isDead = DEAD_STATUSES.has(packet.status);
  const isWritable = WRITABLE_STATUSES.has(packet.status);
  const gateUnlocked = sessionToken != null && (packet.documents?.length ?? 0) > 0;

  return (
    <div className="min-h-screen text-gray-900 antialiased" style={pageStyle}>
      <div
        aria-hidden="true"
        style={{
          height: 4,
          backgroundImage: `linear-gradient(90deg, ${primary}, ${branding.secondary_color}, ${accent})`,
        }}
      />
      <header className="border-b border-gray-200" style={{ backgroundColor: branding.surface_color_light }}>
        <div className="mx-auto max-w-3xl px-6 sm:px-10 py-4 flex items-center gap-3 min-w-0">
          {branding.logo_url && !logoError ? (
            <img
              src={branding.logo_url}
              alt={companyDisplayName}
              width={180}
              height={30}
              referrerPolicy="no-referrer"
              className="object-contain"
              style={{ height: 30, width: 'auto', maxWidth: 180 }}
              onError={() => setLogoError(true)}
            />
          ) : (
            <>
              <div
                className="h-8 w-8 rounded flex items-center justify-center flex-shrink-0 text-white text-sm font-semibold"
                style={{ backgroundColor: primary }}
              >
                {companyDisplayName[0]?.toUpperCase() || 'O'}
              </div>
              <span className="text-[15px] font-semibold text-gray-900 truncate">{companyDisplayName}</span>
            </>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 sm:px-10 py-10 sm:py-14">
        {completed || packet.status === 'completed' ? (
          <CompletionScreen downloadUrl={downloadUrl} accent={accent} />
        ) : packet.status === 'completing' ? (
          <StatusNotice
            title="We're finishing your documents"
            body="Your documents are being finalized. This page will update automatically — please keep it open for a moment."
            accent={accent}
            spinner
          />
        ) : isDead ? (
          <StatusNotice
            title="Link no longer available"
            body="This onboarding link is no longer available. Please contact us for a new link."
            accent={accent}
          />
        ) : packet.status === 'completion_failed' ? (
          <StatusNotice
            title="We're finishing your documents"
            body="We hit a snag finalizing your documents. Our team has been notified and will follow up — no action is needed from you right now."
            accent={accent}
          />
        ) : !gateUnlocked ? (
          <EmailGate
            companyName={companyDisplayName}
            documentCount={packet.document_count}
            statusMessage={packet.status_message}
            email={email}
            onEmailChange={setEmail}
            onSubmit={handleVerify}
            verifying={verifying}
            error={verifyError}
            accent={accent}
          />
        ) : (
          <FillFlow
            token={token!}
            docs={docs}
            docIndex={docIndex}
            currentDoc={currentDoc}
            draftValues={draftValues}
            setFieldValue={setFieldValue}
            onPrev={goPrevDoc}
            onNext={goNextDoc}
            savingDoc={savingDoc}
            docError={docError}
            isWritable={isWritable}
            requiresSignature={requiresSignature}
            sigRef={sigRef}
            sigEmpty={sigEmpty}
            onSigChange={(empty) => {
              setSigEmpty(empty);
              if (!empty) setSignatureSaved(false);
            }}
            signatureSaved={signatureSaved}
            onClearSignature={() => sigRef.current?.clear()}
            onSaveSignature={saveSignature}
            savingSig={savingSig}
            sigError={sigError}
            accent={accent}
            primary={primary}
            esignDisclosure={packet.esign_disclosure}
            allDocsViewed={allDocsViewed}
            missingRequired={missingRequired}
            canSubmit={canSubmit}
            submitting={submitting}
            submitError={submitError}
            onSubmit={handleSubmit}
            requestHeaders={requestHeaders}
          />
        )}
      </main>

      <PublicFooter branding={branding} companyDisplayName={companyDisplayName} />
    </div>
  );
}

// =====================================================================
// Email gate
// =====================================================================

interface EmailGateProps {
  companyName: string;
  documentCount: number;
  statusMessage?: string | null;
  email: string;
  onEmailChange: (v: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  verifying: boolean;
  error: string | null;
  accent: string;
}

function EmailGate({
  companyName,
  documentCount,
  statusMessage,
  email,
  onEmailChange,
  onSubmit,
  verifying,
  error,
  accent,
}: EmailGateProps) {
  return (
    <section className="max-w-md mx-auto text-center">
      <h1 className="text-2xl sm:text-3xl font-semibold text-gray-900 tracking-tight text-balance">
        Welcome to your onboarding
      </h1>
      <p className="mt-3 text-[15px] leading-relaxed text-gray-600 text-pretty">
        {statusMessage?.trim()
          ? statusMessage
          : `${companyName} has prepared ${documentCount} document${documentCount === 1 ? '' : 's'} for you to review and complete. Enter your email to begin.`}
      </p>

      <form onSubmit={onSubmit} className="mt-8 text-left space-y-4">
        <div>
          <label htmlFor="onboarding-email" className="block text-sm font-medium text-gray-700">
            Email address
          </label>
          <input
            id="onboarding-email"
            type="email"
            name="email"
            value={email}
            onChange={(e) => onEmailChange(e.target.value)}
            autoComplete="email"
            inputMode="email"
            spellCheck={false}
            required
            placeholder="you@example.com"
            className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-900 shadow-sm placeholder:text-gray-400 focus-visible:border-gray-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            style={{ outlineColor: accent }}
          />
        </div>

        {error && (
          <p role="alert" aria-live="polite" className="text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={verifying}
          className="inline-flex w-full items-center justify-center gap-2 rounded px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50 transition-opacity"
          style={{ backgroundColor: accent, outlineColor: accent }}
        >
          {verifying && <ArrowPathIcon className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
          {verifying ? 'Verifying…' : 'Continue'}
        </button>
      </form>
    </section>
  );
}

// =====================================================================
// Fill flow (step-through, one document at a time)
// =====================================================================

interface FillFlowProps {
  token: string;
  docs: OnboardingPublicDocument[];
  docIndex: number;
  currentDoc: OnboardingPublicDocument | null;
  draftValues: Record<number, Record<string, string>>;
  setFieldValue: (docId: number, fieldId: string, value: string) => void;
  onPrev: () => void;
  onNext: () => void;
  savingDoc: boolean;
  docError: string | null;
  isWritable: boolean;
  requiresSignature: boolean;
  sigRef: React.Ref<SignatureCanvasHandle>;
  sigEmpty: boolean;
  onSigChange: (empty: boolean) => void;
  signatureSaved: boolean;
  onClearSignature: () => void;
  onSaveSignature: () => Promise<boolean>;
  savingSig: boolean;
  sigError: string | null;
  accent: string;
  primary: string;
  esignDisclosure?: string | null;
  allDocsViewed: boolean;
  missingRequired: string[];
  canSubmit: boolean;
  submitting: boolean;
  submitError: string | null;
  onSubmit: () => void;
  requestHeaders: () => Record<string, string> | undefined;
}

function FillFlow({
  token,
  docs,
  docIndex,
  currentDoc,
  draftValues,
  setFieldValue,
  onPrev,
  onNext,
  savingDoc,
  docError,
  isWritable,
  requiresSignature,
  sigRef,
  sigEmpty,
  onSigChange,
  signatureSaved,
  onClearSignature,
  onSaveSignature,
  savingSig,
  sigError,
  accent,
  primary,
  esignDisclosure,
  allDocsViewed,
  missingRequired,
  canSubmit,
  submitting,
  submitError,
  onSubmit,
  requestHeaders,
}: FillFlowProps) {
  const isLastDoc = docIndex >= docs.length - 1;
  const onSignatureCard = requiresSignature && isLastDoc;

  return (
    <section>
      {/* Stepper */}
      <div className="flex items-center justify-between gap-4">
        <p className="text-xs uppercase tracking-wider text-gray-500" style={{ fontVariantNumeric: 'tabular-nums' }}>
          Document {docs.length === 0 ? 0 : docIndex + 1} of {docs.length}
        </p>
        <div className="flex items-center gap-2" aria-hidden="true">
          {docs.map((d, i) => (
            <span
              key={d.id}
              className="h-1.5 rounded-full transition-[width,background-color] duration-200"
              style={{
                width: i === docIndex ? 24 : 8,
                backgroundColor: i === docIndex ? accent : withAlpha(accent, '40'),
              }}
            />
          ))}
        </div>
      </div>

      {!isWritable && (
        <p role="status" className="mt-4 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
          This packet is read-only right now.
        </p>
      )}

      {currentDoc && (
        <DocumentFiller
          key={currentDoc.id}
          token={token}
          doc={currentDoc}
          values={draftValues[currentDoc.id] ?? currentDoc.field_values}
          onFieldChange={(fieldId, value) => setFieldValue(currentDoc.id, fieldId, value)}
          disabled={!isWritable || savingDoc}
          accent={accent}
          primary={primary}
          requestHeaders={requestHeaders}
        />
      )}

      {docError && (
        <p role="alert" aria-live="polite" className="mt-4 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
          {docError}
        </p>
      )}

      {/* Signature — drawn once on the last document, reused across all. */}
      {onSignatureCard && (
        <div className="mt-8 rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex items-center gap-2 mb-2">
            <PencilSquareIcon className="h-5 w-5 text-gray-500" aria-hidden="true" />
            <h2 className="text-base font-semibold text-gray-900">Your signature</h2>
          </div>
          <p className="text-sm text-gray-600 mb-4 text-pretty">
            Draw your signature once below. It will be applied to every document that requires a signature.
          </p>
          <SignatureCanvas ref={sigRef} accentHex={accent} onSignatureChange={onSigChange} disabled={savingSig} />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onClearSignature}
              disabled={savingSig}
              className="text-sm font-medium text-gray-600 hover:text-gray-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded disabled:opacity-50"
              style={{ outlineColor: accent }}
            >
              Clear
            </button>
            <button
              type="button"
              onClick={() => void onSaveSignature()}
              disabled={sigEmpty || savingSig || signatureSaved}
              className="inline-flex items-center gap-2 rounded px-4 py-2 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50 transition-opacity"
              style={{ backgroundColor: accent, outlineColor: accent }}
            >
              {savingSig && <ArrowPathIcon className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
              {signatureSaved ? 'Signature saved' : 'Save signature'}
            </button>
            {signatureSaved && !sigEmpty && (
              <span className="inline-flex items-center gap-1 text-sm text-green-700" role="status">
                <CheckIcon className="h-4 w-4" aria-hidden="true" /> Saved
              </span>
            )}
          </div>
          {sigError && (
            <p role="alert" aria-live="polite" className="mt-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
              {sigError}
            </p>
          )}
          {esignDisclosure !== undefined && (
            <details className="group mt-4 text-sm">
              <summary className="cursor-pointer font-medium text-gray-700 hover:text-gray-900 list-none flex items-center gap-2 select-none">
                <span aria-hidden="true" className="inline-block transition-transform group-open:rotate-90">▸</span>
                Electronic signature disclosure &amp; consent
              </summary>
              <div className="mt-3 space-y-2 text-[13px] leading-relaxed text-gray-600 text-pretty">
                {(esignDisclosure ?? FALLBACK_ESIGN_DISCLOSURE).split('\n\n').map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {/* Step navigation */}
      <div className="mt-8 flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={onPrev}
          disabled={docIndex === 0 || savingDoc}
          aria-label="Previous document"
          className="inline-flex items-center gap-2 rounded px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 shadow-sm hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-400 disabled:opacity-50"
        >
          <ArrowLeftIcon className="h-4 w-4" aria-hidden="true" />
          Back
        </button>

        {isLastDoc ? null : (
          <button
            type="button"
            onClick={onNext}
            disabled={savingDoc}
            aria-label="Next document"
            className="inline-flex items-center gap-2 rounded px-5 py-2 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50 transition-opacity"
            style={{ backgroundColor: primary, outlineColor: primary }}
          >
            {savingDoc ? 'Saving…' : 'Next'}
            <ArrowRightIcon className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>

      {/* Submit — only on the last document */}
      {isLastDoc && (
        <div className="mt-8 border-t border-gray-200 pt-8">
          {!allDocsViewed && (
            <p role="status" className="mb-4 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
              Please step through every document before submitting.
            </p>
          )}
          {missingRequired.length > 0 && (
            <div role="status" className="mb-4 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
              <p className="font-medium">Please complete the required fields:</p>
              <ul className="mt-1 list-disc list-inside space-y-0.5">
                {missingRequired.slice(0, 6).map((m) => (
                  <li key={m} className="break-words">{m}</li>
                ))}
                {missingRequired.length > 6 && <li>…and {missingRequired.length - 6} more.</li>}
              </ul>
            </div>
          )}
          {requiresSignature && !signatureSaved && (
            <p role="status" className="mb-4 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
              Please draw and save your signature above before submitting.
            </p>
          )}
          {submitError && (
            <p role="alert" aria-live="polite" className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
              {submitError}
            </p>
          )}
          <button
            type="button"
            onClick={onSubmit}
            disabled={!canSubmit}
            className="inline-flex w-full items-center justify-center gap-2 rounded px-5 py-3 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50 transition-opacity"
            style={{ backgroundColor: accent, outlineColor: accent }}
          >
            {submitting && <ArrowPathIcon className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
            {submitting ? 'Submitting…' : 'Submit documents'}
          </button>
        </div>
      )}
    </section>
  );
}

// =====================================================================
// Document filler — pdf.js canvas + editable field inputs overlaid
// =====================================================================

interface DocumentFillerProps {
  token: string;
  doc: OnboardingPublicDocument;
  values: Record<string, string>;
  onFieldChange: (fieldId: string, value: string) => void;
  disabled: boolean;
  accent: string;
  primary: string;
  requestHeaders: () => Record<string, string> | undefined;
}

function DocumentFiller({
  token,
  doc,
  values,
  onFieldChange,
  disabled,
  accent,
  primary,
  requestHeaders,
}: DocumentFillerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const docRef = useRef<PDFDocumentProxy | null>(null);
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const [pageCount, setPageCount] = useState(0);
  const [pageIdx, setPageIdx] = useState(0);
  const [canvasSize, setCanvasSize] = useState<{ w: number; h: number } | null>(null);
  const [loadingDoc, setLoadingDoc] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // CSS scale applied to fit the natural-width canvas into a narrow viewport
  // (mobile). The overlay inputs are positioned in natural canvas pixels and
  // scaled by the same factor so they stay glued to the PDF fields.
  const [displayScale, setDisplayScale] = useState(1);

  // (Re)load the per-packet PDF for this document. The bytes are streamed by
  // the session-gated endpoint, so we fetch as a blob with the session header
  // and hand pdf.js the object URL.
  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setLoadingDoc(true);
    setError(null);
    setCanvasSize(null);

    (async () => {
      try {
        const res = await publicClient.get<Blob>(
          `/api/onboarding/public/${token}/documents/${doc.id}/pdf`,
          { responseType: 'blob', headers: requestHeaders() },
        );
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        const loadingTask = getDocument(objectUrl);
        const pdf = await loadingTask.promise;
        if (cancelled) {
          void pdf.destroy();
          return;
        }
        docRef.current = pdf;
        setPageCount(pdf.numPages);
        // Seed to the first page that actually has a field, so single-field
        // documents don't open on a blank cover page.
        const firstFieldPage = doc.field_definitions[0]?.page;
        setPageIdx(firstFieldPage ? clamp(firstFieldPage - 1, 0, pdf.numPages - 1) : 0);
        setLoadingDoc(false);
      } catch (err) {
        if (cancelled) return;
        setLoadingDoc(false);
        setError(publicErrorMessage(err, 'We could not load this document. Please try again.'));
      }
    })();

    return () => {
      cancelled = true;
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel();
        renderTaskRef.current = null;
      }
      if (docRef.current) {
        void docRef.current.destroy();
        docRef.current = null;
      }
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [token, doc.id, doc.field_definitions, requestHeaders]);

  // Render the active page to the canvas at RENDER_SCALE (natural pixels).
  useEffect(() => {
    const pdf = docRef.current;
    const canvas = canvasRef.current;
    if (!pdf || !canvas || loadingDoc) return;
    let cancelled = false;
    void (async () => {
      try {
        if (renderTaskRef.current) {
          renderTaskRef.current.cancel();
          renderTaskRef.current = null;
        }
        const page = await pdf.getPage(pageIdx + 1);
        if (cancelled) return;
        const viewport = page.getViewport({ scale: RENDER_SCALE });
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        const task = page.render({ canvasContext: ctx, viewport });
        renderTaskRef.current = task;
        try {
          await task.promise;
        } catch (err) {
          const name = (err as { name?: string } | undefined)?.name;
          if (name === 'RenderingCancelledException') return;
          throw err;
        }
        if (cancelled) return;
        setCanvasSize({ w: viewport.width, h: viewport.height });
      } catch (err) {
        if (cancelled) return;
        setError(publicErrorMessage(err, 'We could not render this page. Please try again.'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pageIdx, loadingDoc]);

  // Fit the natural-width canvas to the container so the page (and its
  // overlaid inputs) scales down on narrow screens. Recomputed on resize.
  useEffect(() => {
    if (!canvasSize) return;
    const recompute = () => {
      const container = containerRef.current;
      if (!container) return;
      const available = container.clientWidth;
      const scale = available > 0 && canvasSize.w > available ? available / canvasSize.w : 1;
      setDisplayScale(scale);
    };
    recompute();
    window.addEventListener('resize', recompute, { passive: true });
    return () => window.removeEventListener('resize', recompute);
  }, [canvasSize]);

  const goPrev = () => setPageIdx((i) => Math.max(0, i - 1));
  const goNext = () => setPageIdx((i) => Math.min(pageCount - 1, i + 1));

  // Fields visible on the current page, positioned in natural canvas pixels.
  const visibleFields: Array<{ field: OnboardingFieldDefinition; box: DrawnBox }> = [];
  if (canvasSize) {
    for (const field of doc.field_definitions) {
      if (field.page - 1 === pageIdx) {
        visibleFields.push({ field, box: pdfCoordsToBox(field, canvasSize.h) });
      }
    }
  }

  return (
    <div className="mt-6">
      <p className="text-sm font-medium text-gray-900 truncate" title={doc.original_filename}>
        {doc.original_filename}
      </p>

      {/* Page nav */}
      {pageCount > 1 && (
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={goPrev}
            disabled={pageIdx === 0 || loadingDoc}
            aria-label="Previous page"
            className="inline-flex items-center justify-center h-8 w-8 rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-400 disabled:opacity-50"
          >
            <ArrowLeftIcon className="h-4 w-4" aria-hidden="true" />
          </button>
          <span className="text-sm text-gray-700" style={{ fontVariantNumeric: 'tabular-nums' }}>
            Page {pageCount === 0 ? 0 : pageIdx + 1} of {pageCount}
          </span>
          <button
            type="button"
            onClick={goNext}
            disabled={pageIdx >= pageCount - 1 || loadingDoc}
            aria-label="Next page"
            className="inline-flex items-center justify-center h-8 w-8 rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-400 disabled:opacity-50"
          >
            <ArrowRightIcon className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      )}

      <div
        ref={containerRef}
        className="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-2 sm:p-3 overflow-auto"
      >
        {loadingDoc && (
          <div className="flex items-center gap-2 text-sm text-gray-500 p-6">
            <ArrowPathIcon className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            Loading document…
          </div>
        )}
        {error && (
          <p role="alert" aria-live="polite" className="text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
            {error}
          </p>
        )}
        {!loadingDoc && !error && (
          // The scaled wrapper sizes to the displayed (scaled) canvas so the
          // overlay's percentage-free absolute inputs line up. We scale via an
          // explicit width/height box + transform on the inner natural-size
          // layer to keep input fonts crisp.
          <div
            className="relative mx-auto"
            style={
              canvasSize
                ? { width: canvasSize.w * displayScale, height: canvasSize.h * displayScale }
                : undefined
            }
          >
            <div
              className="absolute left-0 top-0 origin-top-left"
              style={{ transform: `scale(${displayScale})` }}
            >
              <canvas ref={canvasRef} className="block bg-white shadow-sm" aria-label={`${doc.original_filename} page ${pageIdx + 1}`} />
              {canvasSize &&
                visibleFields.map(({ field, box }) => (
                  <FieldInput
                    key={field.id}
                    field={field}
                    box={box}
                    value={values[field.id] ?? ''}
                    onChange={(v) => onFieldChange(field.id, v)}
                    disabled={disabled}
                    accent={accent}
                    primary={primary}
                  />
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// =====================================================================
// A single overlaid editable field
// =====================================================================

interface FieldInputProps {
  field: OnboardingFieldDefinition;
  box: DrawnBox;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  accent: string;
  primary: string;
}

function FieldInput({ field, box, value, onChange, disabled, accent, primary }: FieldInputProps) {
  const common = {
    value,
    disabled,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(e.target.value),
    'aria-label': field.label || field.id,
    name: field.id,
    autoComplete: 'off',
    placeholder: field.description?.trim() || field.label || undefined,
    className:
      'absolute box-border w-full h-full rounded-sm border bg-white/95 px-1 py-0.5 text-[13px] text-gray-900 shadow-sm placeholder:text-gray-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 disabled:bg-gray-100',
    style: { left: 0, top: 0, borderColor: withAlpha(primary, '99'), outlineColor: accent } as React.CSSProperties,
  };

  const wrapperStyle: React.CSSProperties = {
    left: `${box.leftPx}px`,
    top: `${box.topPx}px`,
    width: `${box.widthPx}px`,
    height: `${box.heightPx}px`,
  };

  // Signature fields are NOT typed — the drawn signature covers them. Show a
  // non-interactive marker so the client knows a signature lands here.
  if (field.kind === 'signature') {
    return (
      <div
        className="absolute flex items-center justify-center rounded-sm border-2 border-dashed text-[11px] font-medium"
        style={{ ...wrapperStyle, borderColor: withAlpha(accent, '99'), color: accent, backgroundColor: withAlpha(accent, '10') }}
        aria-hidden="true"
      >
        {field.label || 'Signature'}
      </div>
    );
  }

  return (
    <div className="absolute" style={wrapperStyle}>
      {field.kind === 'address' ? (
        <textarea {...common} inputMode="text" rows={2} />
      ) : field.kind === 'date' ? (
        <input {...common} type="date" inputMode="numeric" />
      ) : (
        <input {...common} type="text" inputMode="text" />
      )}
    </div>
  );
}

// =====================================================================
// Completion + status screens
// =====================================================================

function CompletionScreen({ downloadUrl, accent }: { downloadUrl: string | null; accent: string }) {
  // The server returns app-relative download paths; prefix with the API origin
  // (when set) so the no-login proxy link resolves to the backend in prod —
  // same convention as ProposalAttachmentsSection. Absolute URLs pass through.
  const apiBase = import.meta.env.VITE_API_URL || '';
  const resolveUrl = (url: string) => (/^https?:\/\//i.test(url) ? url : `${apiBase}${url}`);

  // Fetch the signed-PDF list from the in-session download landing URL. When
  // there's no in-session URL (e.g. after a reload, or a background-completed
  // poll), we fall back to the "arrive by email" copy — the e-mailed link works.
  const [downloads, setDownloads] = useState<OnboardingDownloadDocument[]>([]);
  useEffect(() => {
    if (!downloadUrl) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await publicClient.get<{ documents: OnboardingDownloadDocument[] }>(
          resolveUrl(downloadUrl),
        );
        if (!cancelled) setDownloads(res.data.documents ?? []);
      } catch (err) {
        // Fall back to the e-mailed copy — never block the success screen — but
        // log so a systemic landing-endpoint outage is observable rather than
        // silently indistinguishable from "no documents".
        console.warn('onboarding: in-session download list fetch failed', err);
      }
    })();
    return () => {
      cancelled = true;
    };
    // resolveUrl is a pure derivation of apiBase (stable); only the URL matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [downloadUrl]);
  return (
    <section className="max-w-md mx-auto text-center">
      <div
        className="mx-auto flex h-12 w-12 items-center justify-center rounded-full"
        style={{ backgroundColor: withAlpha(accent, '1a') }}
      >
        <CheckIcon className="h-6 w-6" style={{ color: accent }} aria-hidden="true" />
      </div>
      <h1 className="mt-4 text-2xl font-semibold text-gray-900 tracking-tight">All done — thank you</h1>
      <p className="mt-2 text-sm text-gray-600 leading-relaxed text-pretty">
        Your documents have been submitted. A copy has been emailed to you. You can also download them below.
      </p>

      {downloads.length > 0 ? (
        <div className="mt-8 text-left space-y-2">
          {downloads.map((d) => (
            <a
              key={d.doc_id}
              href={resolveUrl(d.url)}
              target="_blank"
              rel="noreferrer"
              referrerPolicy="no-referrer"
              className="flex items-center justify-between gap-3 rounded border border-gray-200 bg-white px-4 py-3 text-sm font-medium text-gray-900 shadow-sm hover:border-gray-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              style={{ outlineColor: accent }}
            >
              <span className="truncate">{d.title}</span>
              <span className="text-xs font-semibold" style={{ color: accent }}>Download</span>
            </a>
          ))}
        </div>
      ) : (
        <p className="mt-6 text-sm text-gray-500">
          Your signed copies will arrive by email shortly. You can safely close this page.
        </p>
      )}
    </section>
  );
}

function StatusNotice({
  title,
  body,
  accent,
  spinner,
}: {
  title: string;
  body: string;
  accent: string;
  spinner?: boolean;
}) {
  return (
    <section className="max-w-md mx-auto text-center" role="status" aria-live="polite">
      {spinner && (
        <ArrowPathIcon
          className="mx-auto h-8 w-8 animate-spin motion-reduce:animate-none"
          style={{ color: accent }}
          aria-hidden="true"
        />
      )}
      <h1 className="mt-4 text-2xl font-semibold text-gray-900 tracking-tight">{title}</h1>
      <p className="mt-2 text-sm text-gray-600 leading-relaxed text-pretty">{body}</p>
    </section>
  );
}

// =====================================================================
// Footer
// =====================================================================

function PublicFooter({
  branding,
  companyDisplayName,
}: {
  branding: OnboardingPublicBranding;
  companyDisplayName: string;
}) {
  return (
    <footer
      className="mt-16 border-t border-gray-200"
      style={{ backgroundColor: branding.surface_color_light, paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <div className="mx-auto max-w-3xl px-6 sm:px-10 py-8 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-gray-900">{companyDisplayName}</p>
          {branding.footer_text && (
            <p className="text-xs text-gray-500 leading-relaxed max-w-sm">{branding.footer_text}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
          {branding.terms_of_service_url && (
            <a href={branding.terms_of_service_url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer" className="hover:text-gray-700">
              Terms of Service
            </a>
          )}
          {branding.privacy_policy_url && (
            <a href={branding.privacy_policy_url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer" className="hover:text-gray-700">
              Privacy Policy
            </a>
          )}
        </div>
      </div>
    </footer>
  );
}

export default PublicOnboardingView;

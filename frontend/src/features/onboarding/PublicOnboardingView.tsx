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
  OnboardingQuestionnaireField,
  OnboardingAnswerValue,
  OnboardingDocumentKind,
} from '../../types';
import { OTHER_OPTION_TOKEN } from '../../types';
import { ONBOARDING_UPLOAD_ACCEPT } from './uploadConstants';

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

// --- session-scoped persistence (QOL) --------------------------------------
// The bearer session + the last document index are cached in sessionStorage so
// an accidental reload / back-nav doesn't drop the signer back at the e-mail
// gate (their answers are already server-saved; this preserves the SESSION).
// sessionStorage — NOT localStorage: scoped to the tab, cleared on close, and
// the token self-expires server-side after SESSION_TTL (45 min) regardless, so
// nothing usable outlives the fill. Versioned keys + try/catch (private mode /
// quota / disabled storage throw — persistence is best-effort, never fatal).
const SESSION_STORE_PREFIX = 'onboardingSession:v1:';
const DOCINDEX_STORE_PREFIX = 'onboardingDocIndex:v1:';
const SESSION_TIMEOUT_NOTICE =
  'Your session timed out for security. Re-enter your email to pick up where ' +
  'you left off — your answers are saved.';

function safeSessionGet(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}
function safeSessionSet(key: string, value: string): void {
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    /* private mode / quota — best-effort */
  }
}
function safeSessionRemove(key: string): void {
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

// Per-document draft of answers, widened in v3 to carry choice lists + the
// Other write-in shape (the FE half of P0-1). Keyed doc id → field id → answer.
type DraftValues = Record<number, Record<string, OnboardingAnswerValue>>;

// The doc's render kind, defaulting to the legacy pdf.js canvas when the server
// payload predates the v3 discriminator (so the page never breaks mid-deploy).
function docKind(doc: OnboardingPublicDocument): OnboardingDocumentKind {
  return doc.kind ?? 'esign_pdf';
}

/** True iff this document renders the v3 form UI (not the pdf.js canvas). */
function isFormDoc(doc: OnboardingPublicDocument): boolean {
  return docKind(doc) !== 'esign_pdf';
}

// --- questionnaire answer helpers (the {value, other} write-in shape) ------

/** The selected option value(s) for a choice answer, ignoring the write-in. */
function selectedValues(answer: OnboardingAnswerValue | undefined): string[] {
  if (answer == null) return [];
  if (typeof answer === 'string') return answer ? [answer] : [];
  if (Array.isArray(answer)) return answer;
  // { value, other } shape
  const inner = answer.value;
  if (inner == null) return [];
  return Array.isArray(inner) ? inner : [inner];
}

/** The Other write-in text for a choice answer (empty when none). */
function otherText(answer: OnboardingAnswerValue | undefined): string {
  if (answer && typeof answer === 'object' && !Array.isArray(answer)) {
    return answer.other ?? '';
  }
  return '';
}

/** True iff a questionnaire field's required answer is present + complete. */
function questionnaireFieldSatisfied(
  field: OnboardingQuestionnaireField,
  answer: OnboardingAnswerValue | undefined,
): boolean {
  if (!field.required) return true;
  // Sensitive text fields store None in field_values (the plaintext is encrypted
  // into the secret table server-side), so after a 409-refetch reseed the local
  // value is undefined and the client can't re-derive whether it's "filled" — the
  // server holds the ciphertext. Treat a sensitive required field as satisfied so
  // a refetch never permanently blocks Submit. (The real required-check is the
  // server's required_satisfied against the secrets table.)
  if (field.sensitive) return true;
  if (field.kind === 'file_upload') {
    // Uploads are reflected back as a list of upload ids under the field id.
    return Array.isArray(answer) && answer.length > 0;
  }
  if (
    field.kind === 'single_choice' ||
    field.kind === 'multi_choice'
  ) {
    const values = selectedValues(answer);
    if (values.length === 0) return false;
    if (values.includes(OTHER_OPTION_TOKEN)) {
      return otherText(answer).trim().length > 0;
    }
    return true;
  }
  // text / paragraph / email / url / date → non-empty string
  return typeof answer === 'string' && answer.trim().length > 0;
}

/**
 * The answers to PATCH for a doc, EXCLUDING file_upload fields. Per §C.2 uploads
 * bypass the version-fence PATCH — the dedicated /files (POST/DELETE) endpoint is
 * the sole writer of ``field_values[file_field]`` server-side, and the backend's
 * upload_request.validate_value rejects the FE's reflected string ids (it expects
 * the int upload-row ids it writes itself). Sending them 422s the whole save, so
 * an upload_request packet with a file could never persist its text answers /
 * complete. We keep the reflected ids in local draftValues (for the on-screen
 * file list + the required-check) and simply never PATCH them.
 */
function patchableValues(
  doc: OnboardingPublicDocument,
  draft: Record<string, OnboardingAnswerValue> | undefined,
): Record<string, OnboardingAnswerValue> {
  if (!draft) return {};
  if (!isFormDoc(doc)) return draft; // esign: every field is patchable
  const fileFieldIds = new Set(
    (doc.field_definitions as OnboardingQuestionnaireField[])
      .filter((f) => f.kind === 'file_upload')
      .map((f) => f.id),
  );
  if (fileFieldIds.size === 0) return draft;
  const out: Record<string, OnboardingAnswerValue> = {};
  for (const [fid, value] of Object.entries(draft)) {
    if (!fileFieldIds.has(fid)) out[fid] = value;
  }
  return out;
}

function PublicOnboardingView() {
  const { token } = useParams<{ token: string }>();

  const [packet, setPacket] = useState<OnboardingPublicPacket | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [logoError, setLogoError] = useState(false);

  // Bearer session token returned by /verify. Cached in sessionStorage (NOT a
  // cookie/localStorage) and re-seeded on mount so a reload / accidental nav
  // skips the e-mail gate instead of forcing re-verification. Attached to every
  // request; if it's stale the first call 401s → handleSessionExpired clears it.
  const sessionStoreKey = token ? `${SESSION_STORE_PREFIX}${token}` : null;
  const docIndexStoreKey = token ? `${DOCINDEX_STORE_PREFIX}${token}` : null;
  const [sessionToken, setSessionToken] = useState<string | null>(() =>
    sessionStoreKey ? safeSessionGet(sessionStoreKey) : null,
  );
  const sessionTokenRef = useRef<string | null>(null);
  sessionTokenRef.current = sessionToken;
  // Shown on the e-mail gate after a session times out / is dropped, so the
  // signer understands why they're being asked to re-verify (answers are safe).
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);

  // Email-gate state.
  const [email, setEmail] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  // Step-through state — one document at a time. Seeded from sessionStorage so a
  // reload lands the signer back on the document they were filling, not Doc 1
  // (clamped to the real doc count once documents load; cleared on completion).
  const [docIndex, setDocIndex] = useState<number>(() => {
    const raw = docIndexStoreKey ? safeSessionGet(docIndexStoreKey) : null;
    const n = raw ? Number.parseInt(raw, 10) : 0;
    return Number.isInteger(n) && n >= 0 ? n : 0;
  });
  // Local draft of field values per document, seeded from the server payload and
  // the source of truth for the inputs. Widened in v3 (the FE half of P0-1) to
  // carry choice lists + the Other write-in shape, not just strings.
  const [draftValues, setDraftValues] = useState<DraftValues>({});
  // Per-document version captured for the optimistic-lock PATCH ``base_version``.
  const [docVersions, setDocVersions] = useState<Record<number, number>>({});
  // Which documents the client has stepped to / saved (every-doc-viewed gate).
  const [viewedDocIds, setViewedDocIds] = useState<Set<number>>(() => new Set());
  const [savingDoc, setSavingDoc] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  // Docs that have had at least one successful save this session — gates the
  // "All changes saved" reassurance so it never shows on a pristine, untouched
  // doc (only after the signer's answers have actually been persisted).
  const savedDocsRef = useRef<Set<number>>(new Set());

  // Signature drawn once, reused across all documents. Typed non-null so the
  // ref is assignable to the forwardRef ``ref`` prop (the imperative handle is
  // populated by SignatureCanvas; we still guard with optional chaining).
  const sigRef = useRef<SignatureCanvasHandle>(null);
  const [sigEmpty, setSigEmpty] = useState(true);
  const [signatureVersion, setSignatureVersion] = useState<number>(0);
  const [signatureSaved, setSignatureSaved] = useState(false);
  const [savingSig, setSavingSig] = useState(false);
  const [sigError, setSigError] = useState<string | null>(null);

  // E-records consent — its own affirmative step BEFORE the signature (§D).
  const [consentRecorded, setConsentRecorded] = useState(false);
  const [recordingConsent, setRecordingConsent] = useState(false);
  const [consentError, setConsentError] = useState<string | null>(null);

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

  // Drop the (expired/invalid) session and fall back to the e-mail gate with a
  // reassuring notice. Called on any 401 — the server returns 401 from
  // require_session once the 45-min token expires. Answers are already saved, so
  // re-verifying simply re-issues a session and reloads the saved field_values.
  const handleSessionExpired = useCallback(() => {
    sessionTokenRef.current = null;
    setSessionToken(null);
    if (sessionStoreKey) safeSessionRemove(sessionStoreKey);
    setSessionNotice(SESSION_TIMEOUT_NOTICE);
  }, [sessionStoreKey]);

  // --- Initial load (pre-gate) -------------------------------------------
  // Self-reference for the 401 re-fetch (drop the stale session, reload pre-gate
  // branding/counts so the gate renders branded) without a recursive useCallback.
  const fetchPacketRef = useRef<() => Promise<void>>();
  const fetchPacket = useCallback(async () => {
    if (!token) return;
    const sentWithSession = sessionTokenRef.current != null;
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
      if (status === 401 && sentWithSession) {
        // A cached session expired between visits → drop it and reload pre-gate
        // (no session header now) so the branded gate shows with the notice.
        handleSessionExpired();
        await fetchPacketRef.current?.();
        return;
      }
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
  }, [token, requestHeaders, handleSessionExpired]);
  fetchPacketRef.current = fetchPacket;

  useEffect(() => {
    void fetchPacket();
  }, [fetchPacket]);

  useEffect(() => {
    setLogoError(false);
  }, [packet?.branding?.logo_url]);

  // Seed local draft + version state whenever the post-gate documents arrive.
  // ``field_values`` from the server is authoritative on (re)load. A draft is
  // seeded on first sight, AND re-adopted from the server when the server
  // version moves past what we last seeded — that's the 409 path (someone else
  // edited): a refetch must actually overwrite the now-stale local draft, not
  // keep showing the user's stale values. ``seededVersions`` is a ref so a
  // normal in-progress edit (no refetch → documents identity unchanged → this
  // effect doesn't run) is never clobbered mid-typing.
  const documents = packet?.documents;
  const seededVersionsRef = useRef<Record<number, number>>({});
  useEffect(() => {
    if (!documents) return;
    setDraftValues((prev) => {
      const next = { ...prev };
      for (const doc of documents) {
        const seeded = seededVersionsRef.current[doc.id];
        if (next[doc.id] === undefined || seeded !== doc.field_values_version) {
          next[doc.id] = { ...doc.field_values };
        }
      }
      return next;
    });
    for (const doc of documents) {
      seededVersionsRef.current[doc.id] = doc.field_values_version;
    }
    setDocVersions((prev) => {
      const next = { ...prev };
      for (const doc of documents) next[doc.id] = doc.field_values_version;
      return next;
    });
    if (packet?.signature_version !== undefined) {
      setSignatureVersion(packet.signature_version);
    }
    if (packet?.has_signature) setSignatureSaved(true);
    if (packet?.has_consented) setConsentRecorded(true);
  }, [documents, packet?.signature_version, packet?.has_signature, packet?.has_consented]);

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
      // Cache the session so a reload skips the gate (cleared on tab close /
      // 401). Clear any prior timeout notice — we're back in.
      if (sessionStoreKey) safeSessionSet(sessionStoreKey, newToken);
      setSessionNotice(null);
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

  // Persist the position so a reload resumes here…
  useEffect(() => {
    if (docIndexStoreKey) safeSessionSet(docIndexStoreKey, String(docIndex));
  }, [docIndexStoreKey, docIndex]);
  // …clamped to the loaded doc count (a stored index past a now-shorter packet
  // must not strand the signer on a blank step).
  useEffect(() => {
    if (docs.length > 0 && docIndex > docs.length - 1) setDocIndex(docs.length - 1);
  }, [docs.length, docIndex]);

  // On completion the flow is finished — drop the cached session + position so a
  // shared device can't reload back into a now-completed packet's session.
  useEffect(() => {
    if (!completed) return;
    if (sessionStoreKey) safeSessionRemove(sessionStoreKey);
    if (docIndexStoreKey) safeSessionRemove(docIndexStoreKey);
  }, [completed, sessionStoreKey, docIndexStoreKey]);

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

  // For a QUESTIONNAIRE / UPLOAD doc (no PDF stream), the server view-gate is
  // satisfied only by POST /viewed — an esign doc records the view as a side
  // effect of its /pdf byte stream, but a form doc has none, so without this the
  // server's _assert_all_viewed would 422 /complete forever (the P0-4 bug,
  // relocated). Idempotent server-side; a client-side guard ref avoids a
  // duplicate POST per doc. esign docs are skipped here (the /pdf GET handles
  // them) so the legally-meaningful read-before-sign record stays on /pdf.
  const viewedPostedRef = useRef<Set<number>>(new Set());
  useEffect(() => {
    if (!token || currentDoc == null || !isFormDoc(currentDoc)) return;
    if (viewedPostedRef.current.has(currentDoc.id)) return;
    viewedPostedRef.current.add(currentDoc.id);
    const docId = currentDoc.id;
    void (async () => {
      try {
        await publicClient.post(
          `/api/onboarding/public/${token}/documents/${docId}/viewed`,
          {},
          { headers: requestHeaders() },
        );
      } catch (err) {
        // A failed view-mark must not block the page; allow a retry on the next
        // render by clearing the guard. Logged so a systemic outage is visible.
        viewedPostedRef.current.delete(docId);
        console.warn('onboarding: POST /viewed failed', err);
      }
    })();
  }, [token, currentDoc, requestHeaders]);

  const setFieldValue = useCallback(
    (docId: number, fieldId: string, value: OnboardingAnswerValue) => {
      setDraftValues((curr) => ({
        ...curr,
        [docId]: { ...(curr[docId] ?? {}), [fieldId]: value },
      }));
    },
    [],
  );

  const saveDocument = useCallback(
    async (doc: OnboardingPublicDocument): Promise<boolean> => {
      if (!token) return false;
      setSavingDoc(true);
      setDocError(null);
      try {
        const res = await publicClient.patch<{ field_values_version: number }>(
          `/api/onboarding/public/${token}/documents/${doc.id}`,
          {
            // file_upload answers are written by the /files endpoint, not here —
            // see patchableValues (§C.2: uploads bypass the version-fence PATCH).
            field_values: patchableValues(doc, draftValues[doc.id]),
            base_version: docVersions[doc.id] ?? doc.field_values_version,
          },
          { headers: requestHeaders() },
        );
        setDocVersions((curr) => ({ ...curr, [doc.id]: res.data.field_values_version }));
        savedDocsRef.current.add(doc.id);
        return true;
      } catch (err) {
        const status = errorStatus(err);
        if (status === 401) {
          // Session timed out mid-fill → back to the gate (answers are saved).
          handleSessionExpired();
        } else if (status === 409) {
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
    [token, draftValues, docVersions, requestHeaders, fetchPacket, handleSessionExpired],
  );

  // --- Debounced autosave + unsaved-changes guard (Form 2 = 18 required
  // paragraphs — a reload must not lose answers; §7.4). The snapshot is the
  // last-saved draft per doc; a draft that differs is "dirty" → a debounced
  // PATCH persists it and a beforeunload warns if the user leaves first.
  const savedSnapshotRef = useRef<Record<number, string>>({});
  const isDocDirty = useCallback(
    (docId: number): boolean => {
      const snapshot = savedSnapshotRef.current[docId];
      // No snapshot yet → the doc hasn't been seeded as a baseline this render;
      // treat as clean so the first render never transiently arms beforeunload.
      if (snapshot === undefined) return false;
      return JSON.stringify(draftValues[docId] ?? {}) !== snapshot;
    },
    [draftValues],
  );

  // Record a saved snapshot whenever a doc's persisted version advances (the
  // PATCH succeeded) OR the server (re)seeds it — so the dirty check is honest.
  useEffect(() => {
    for (const doc of docs) {
      const saved = draftValues[doc.id];
      if (saved !== undefined && savedSnapshotRef.current[doc.id] === undefined) {
        savedSnapshotRef.current[doc.id] = JSON.stringify(saved);
      }
    }
  }, [docs, draftValues]);

  // Debounced autosave of the open FORM document. esign docs autosave on
  // Next/Submit only (the canvas inputs are small); a long questionnaire saves
  // as you type so a reload never loses 18 paragraphs of answers.
  const autosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const packetWritable = packet != null && WRITABLE_STATUSES.has(packet.status);
  useEffect(() => {
    if (!currentDoc || !isFormDoc(currentDoc) || !packetWritable) return;
    if (!isDocDirty(currentDoc.id)) return;
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    const doc = currentDoc;
    autosaveTimerRef.current = setTimeout(() => {
      autosaveTimerRef.current = null;
      void (async () => {
        const ok = await saveDocument(doc);
        if (ok) {
          savedSnapshotRef.current[doc.id] = JSON.stringify(
            draftValues[doc.id] ?? {},
          );
        }
      })();
    }, 1200);
    return () => {
      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current);
    };
  }, [currentDoc, draftValues, isDocDirty, saveDocument, packetWritable]);

  // Best-effort flush of the OPEN document on hide/unload, so the last
  // sub-debounce keystrokes (and esign field edits, which otherwise only save on
  // Next) aren't lost if the signer closes/backgrounds the tab. Uses fetch +
  // keepalive — axios/XHR is cancelled on unload, keepalive survives it. Kept in
  // a ref so one stable listener fires the freshest closure without re-binding
  // on every keystroke.
  const flushRef = useRef<() => void>(() => {});
  flushRef.current = () => {
    const doc = currentDoc;
    if (!doc || !packetWritable || !token || !isDocDirty(doc.id)) return;
    try {
      void fetch(
        `${publicClient.defaults.baseURL ?? ''}/api/onboarding/public/${token}/documents/${doc.id}`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            ...(sessionTokenRef.current
              ? { 'X-Onboarding-Session': sessionTokenRef.current }
              : {}),
          },
          body: JSON.stringify({
            field_values: patchableValues(doc, draftValues[doc.id]),
            base_version: docVersions[doc.id] ?? doc.field_values_version,
          }),
          keepalive: true,
        },
      );
    } catch {
      /* best-effort on unload */
    }
  };

  // Warn before navigating away with unsaved answers (CLAUDE.md-mandated) AND
  // flush the open doc on hide. Arms only for a writable packet with a dirty doc
  // (form OR esign) so a completed/read-only page never nags or flushes.
  const anyDirty = docs.some((d) => isDocDirty(d.id));
  useEffect(() => {
    if (!anyDirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') flushRef.current();
    };
    const onPageHide = () => flushRef.current();
    window.addEventListener('beforeunload', onBeforeUnload);
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pagehide', onPageHide);
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('pagehide', onPageHide);
    };
  }, [anyDirty]);

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
      if (status === 401) {
        handleSessionExpired();
      } else if (status === 409) {
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
  }, [token, signatureVersion, requestHeaders, fetchPacket, handleSessionExpired]);

  // --- E-records consent (POST /consent) ---------------------------------
  // The affirmative consent step the signer makes BEFORE drawing a signature.
  // Echoes the disclosure version the page rendered so a server-side version
  // change (409) is surfaced rather than silently consenting to stale text.
  const recordConsent = useCallback(async (): Promise<boolean> => {
    if (!token || recordingConsent) return false;
    setRecordingConsent(true);
    setConsentError(null);
    try {
      await publicClient.post(
        `/api/onboarding/public/${token}/consent`,
        { disclosure_version: packet?.esign_disclosure_version ?? null },
        { headers: requestHeaders() },
      );
      setConsentRecorded(true);
      return true;
    } catch (err) {
      const status = errorStatus(err);
      if (status === 401) {
        handleSessionExpired();
      } else if (status === 409) {
        setConsentError('This document was updated. We refreshed it — please review the disclosure and consent again.');
        await fetchPacket();
      } else if (status === 410) {
        setLoadError('This onboarding link is no longer available. Please contact us for a new link.');
      } else {
        setConsentError(publicErrorMessage(err, 'We could not record your consent. Please try again.'));
      }
      return false;
    } finally {
      setRecordingConsent(false);
    }
  }, [token, recordingConsent, packet?.esign_disclosure_version, requestHeaders, fetchPacket, handleSessionExpired]);

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

  // Structured list of every unsatisfied required field across all documents —
  // the focus-first-error flow (PF2) navigates to the first entry's document and
  // focuses its input, and the aggregate summary derives its strings from this.
  const missingRequiredFields = useMemo(() => {
    const out: Array<{
      docId: number;
      docIndex: number;
      field: OnboardingQuestionnaireField | OnboardingFieldDefinition;
      isFormField: boolean;
      label: string;
      docFilename: string;
    }> = [];
    docs.forEach((doc, di) => {
      const values = draftValues[doc.id] ?? doc.field_values;
      const formDoc = isFormDoc(doc);
      for (const f of doc.field_definitions) {
        if (f.kind === 'signature') continue; // covered by the drawn signature
        if (!f.required) continue;
        const satisfied = formDoc
          ? questionnaireFieldSatisfied(
              f as OnboardingQuestionnaireField,
              values[f.id],
            )
          : // esign/text field → non-empty string (the legacy check)
            typeof values[f.id] === 'string' &&
            (values[f.id] as string).trim().length > 0;
        if (!satisfied) {
          out.push({
            docId: doc.id,
            docIndex: di,
            field: f,
            isFormField: formDoc,
            label: f.label,
            docFilename: doc.original_filename,
          });
        }
      }
    });
    return out;
  }, [docs, draftValues]);

  const missingRequired = useMemo(
    () => missingRequiredFields.map((m) => `${m.docFilename}: ${m.label}`),
    [missingRequiredFields],
  );

  // Submit was attempted at least once → surface per-field aria-invalid + inline
  // errors (PF2). They clear live as the user fills each field.
  const [submitAttempted, setSubmitAttempted] = useState(false);

  // Pending focus target captured by handleSubmit; an effect focuses it once the
  // owning document is the one on screen (a cross-document jump re-renders first).
  const pendingFocusRef = useRef<{ docId: number; domId: string } | null>(null);
  useEffect(() => {
    const target = pendingFocusRef.current;
    if (!target || currentDocId !== target.docId) return;
    const el = document.getElementById(target.domId);
    if (el) {
      pendingFocusRef.current = null;
      (el as HTMLElement).focus();
      el.scrollIntoView({ block: 'center' });
    }
  }, [currentDocId]);

  // Everything the server's completion gate also checks. Drives the inline
  // notices; the Submit button itself only blocks on ``submitting`` (PF6) so it
  // stays clickable and the click runs the validate-first flow below.
  const submitReady =
    allDocsViewed &&
    missingRequiredFields.length === 0 &&
    (!requiresSignature || (consentRecorded && signatureSaved));

  // --- Submit (POST /complete) + completion poll -------------------------
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!token || submitting) return;
    // Validate-first (PF2/PF6): the Submit button is no longer hard-disabled, so
    // a click on an incomplete form must surface WHERE the problem is rather than
    // silently no-op. Flip on the per-field error display, then if a required
    // field is unsatisfied jump to its document and focus its input. Bail before
    // any network call until the same gates the server enforces are met.
    if (!submitReady) {
      setSubmitAttempted(true);
      const first = missingRequiredFields[0];
      if (first?.isFormField) {
        const domId =
          first.field.kind === 'file_upload'
            ? `onb-file-${first.docId}-${first.field.id}`
            : `onb-${first.docId}-${first.field.id}`;
        pendingFocusRef.current = { docId: first.docId, domId };
        if (first.docIndex !== docIndex) {
          setDocIndex(first.docIndex);
        } else {
          // Already on the right document — focus now (the effect only fires on
          // a docIndex change).
          const el = document.getElementById(domId);
          if (el) {
            pendingFocusRef.current = null;
            el.focus();
            el.scrollIntoView({ block: 'center' });
          }
        }
      } else if (first) {
        // An esign field (no onb- id on the canvas overlay) — at least navigate
        // to its document so the user sees it; the summary lists the field.
        if (first.docIndex !== docIndex) setDocIndex(first.docIndex);
      }
      return;
    }
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
      if (status === 401) {
        handleSessionExpired();
      } else if (status === 409) {
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
  }, [
    token,
    submitting,
    submitReady,
    missingRequiredFields,
    docIndex,
    currentDoc,
    saveDocument,
    requestHeaders,
    fetchPacket,
    handleSessionExpired,
  ]);

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
            notice={sessionNotice}
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
            savedCurrentDoc={
              currentDoc != null &&
              isFormDoc(currentDoc) &&
              !isDocDirty(currentDoc.id) &&
              savedDocsRef.current.has(currentDoc.id)
            }
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
            consentRecorded={consentRecorded}
            onRecordConsent={recordConsent}
            recordingConsent={recordingConsent}
            consentError={consentError}
            accent={accent}
            primary={primary}
            esignDisclosure={packet.esign_disclosure}
            allDocsViewed={allDocsViewed}
            missingRequired={missingRequired}
            submitAttempted={submitAttempted}
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
  /** Shown above the form after a session timeout (answers are still saved). */
  notice?: string | null;
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
  notice,
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

      {notice && (
        <p
          role="status"
          aria-live="polite"
          className="mt-5 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2 text-left"
        >
          {notice}
        </p>
      )}

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
  draftValues: DraftValues;
  setFieldValue: (
    docId: number,
    fieldId: string,
    value: OnboardingAnswerValue,
  ) => void;
  onPrev: () => void;
  onNext: () => void;
  savingDoc: boolean;
  /** The open form doc is clean + has been saved this session ("All saved"). */
  savedCurrentDoc: boolean;
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
  consentRecorded: boolean;
  onRecordConsent: () => Promise<boolean>;
  recordingConsent: boolean;
  consentError: string | null;
  accent: string;
  primary: string;
  esignDisclosure?: string | null;
  allDocsViewed: boolean;
  missingRequired: string[];
  submitAttempted: boolean;
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
  savedCurrentDoc,
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
  consentRecorded,
  onRecordConsent,
  recordingConsent,
  consentError,
  accent,
  primary,
  esignDisclosure,
  allDocsViewed,
  missingRequired,
  submitAttempted,
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

      {currentDoc && isFormDoc(currentDoc) ? (
        <QuestionnaireFiller
          key={currentDoc.id}
          token={token}
          doc={currentDoc}
          values={draftValues[currentDoc.id] ?? currentDoc.field_values}
          onFieldChange={(fieldId, value) => setFieldValue(currentDoc.id, fieldId, value)}
          // PF1: gate ONLY on read-only state — NEVER on savingDoc. The 1200ms
          // debounced autosave flips savingDoc, and disabling the focused input
          // mid-keystroke yanks the caret to <body> every autosave cycle. Saving
          // is non-blocking; the version-fence 409 reconciles any drift. The
          // passive "Saving…" indicator below replaces the disabled surface.
          disabled={!isWritable}
          savingDoc={savingDoc}
          saved={savedCurrentDoc}
          submitAttempted={submitAttempted}
          accent={accent}
          requestHeaders={requestHeaders}
        />
      ) : currentDoc ? (
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
      ) : null}

      {docError && (
        <p role="alert" aria-live="polite" className="mt-4 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
          {docError}
        </p>
      )}

      {/* E-sign: consent FIRST (affirmative step), then the signature pad. */}
      {onSignatureCard && !consentRecorded && (
        <div className="mt-8 rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="text-base font-semibold text-gray-900 mb-2">
            Before you sign: electronic records &amp; signatures
          </h2>
          <div className="mt-1 max-h-72 space-y-2 overflow-y-auto pr-1 text-[13px] leading-relaxed text-gray-600 text-pretty">
            {(esignDisclosure ?? FALLBACK_ESIGN_DISCLOSURE).split('\n\n').map((para, i) => (
              <p key={i}>{para}</p>
            ))}
          </div>
          {consentError && (
            <p role="alert" aria-live="polite" className="mt-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
              {consentError}
            </p>
          )}
          <button
            type="button"
            onClick={() => void onRecordConsent()}
            disabled={recordingConsent || !isWritable}
            className="mt-4 inline-flex items-center gap-2 rounded px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50 transition-opacity"
            style={{ backgroundColor: accent, outlineColor: accent }}
          >
            {recordingConsent && <ArrowPathIcon className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
            I consent to do business electronically
          </button>
        </div>
      )}

      {/* Signature — drawn once on the last document, reused across all. */}
      {onSignatureCard && consentRecorded && (
        <div className="mt-8 rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex items-center gap-2 mb-2">
            <PencilSquareIcon className="h-5 w-5 text-gray-500" aria-hidden="true" />
            <h2 className="text-base font-semibold text-gray-900">Your signature</h2>
          </div>
          <p className="mb-3 inline-flex items-center gap-1 text-xs text-green-700" role="status">
            <CheckIcon className="h-4 w-4" aria-hidden="true" /> Electronic-records consent recorded
          </p>
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
            <div role="status" aria-live="polite" className="mb-4 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
              <p className="font-medium">Please complete the required fields:</p>
              <ul className="mt-1 list-disc list-inside space-y-0.5">
                {missingRequired.slice(0, 6).map((m) => (
                  <li key={m} className="break-words">{m}</li>
                ))}
                {missingRequired.length > 6 && <li>…and {missingRequired.length - 6} more.</li>}
              </ul>
            </div>
          )}
          {requiresSignature && !consentRecorded && (
            <p role="status" className="mb-4 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
              Please review and accept the electronic-records consent above before submitting.
            </p>
          )}
          {requiresSignature && consentRecorded && !signatureSaved && (
            <p role="status" className="mb-4 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
              Please draw and save your signature above before submitting.
            </p>
          )}
          {submitError && (
            <p role="alert" aria-live="polite" className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
              {submitError}
            </p>
          )}
          {/* PF6: stay enabled until the request starts (gate only on
              ``submitting``). A click on an incomplete form runs the
              validate-first + focus-first-error flow in ``onSubmit`` instead of
              presenting a dead, un-actionable disabled button. */}
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting}
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
// Questionnaire / upload filler — a real form (no PDF canvas)
// =====================================================================

interface QuestionnaireFillerProps {
  token: string;
  doc: OnboardingPublicDocument;
  values: Record<string, OnboardingAnswerValue>;
  onFieldChange: (fieldId: string, value: OnboardingAnswerValue) => void;
  /** Read-only gate only (PF1) — NOT autosave. */
  disabled: boolean;
  /** Drives the passive "Saving…" indicator; never disables the inputs. */
  savingDoc: boolean;
  /** Drives the "All changes saved" reassurance once a save has landed + clean. */
  saved: boolean;
  /** Once true, unsatisfied required fields show aria-invalid + inline error. */
  submitAttempted: boolean;
  accent: string;
  requestHeaders: () => Record<string, string> | undefined;
}

/** A section is a contiguous run of fields sharing a ``section_id`` (first-seen
 * order). Fields with no section_id form one implicit leading group. */
interface FieldSection {
  id: string | null;
  label: string | null;
  fields: OnboardingQuestionnaireField[];
}

function groupSections(
  fields: OnboardingQuestionnaireField[],
): FieldSection[] {
  const sections: FieldSection[] = [];
  for (const field of fields) {
    const sid = field.section_id ?? null;
    const last = sections[sections.length - 1];
    if (last && last.id === sid) {
      last.fields.push(field);
    } else {
      sections.push({
        id: sid,
        label: field.section_label ?? null,
        fields: [field],
      });
    }
  }
  return sections;
}

function QuestionnaireFiller({
  token,
  doc,
  values,
  onFieldChange,
  disabled,
  savingDoc,
  saved,
  submitAttempted,
  accent,
  requestHeaders,
}: QuestionnaireFillerProps) {
  const fields = doc.field_definitions as OnboardingQuestionnaireField[];
  const sections = useMemo(() => groupSections(fields), [fields]);

  return (
    <div className="mt-6">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-gray-900 truncate" title={doc.original_filename}>
          {doc.original_filename}
        </p>
        {/* PF1: passive autosave indicator — never a disabled surface. The
            "saved" reassurance lets the signer trust their answers persisted. */}
        {savingDoc ? (
          <span
            role="status"
            aria-live="polite"
            className="inline-flex flex-shrink-0 items-center gap-1 text-xs text-gray-500"
          >
            <ArrowPathIcon className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            Saving…
          </span>
        ) : saved ? (
          <span
            role="status"
            aria-live="polite"
            className="inline-flex flex-shrink-0 items-center gap-1 text-xs text-green-700"
          >
            <CheckIcon className="h-3.5 w-3.5" aria-hidden="true" />
            All changes saved
          </span>
        ) : null}
      </div>

      <div className="mt-4 space-y-8">
        {sections.map((section, si) => (
          <fieldset
            key={section.id ?? `s${si}`}
            className="rounded-lg border border-gray-200 bg-white p-5"
            disabled={disabled}
          >
            {section.label && (
              <legend className="px-1 text-sm font-semibold text-gray-900">
                {section.label}
              </legend>
            )}
            <div className="space-y-6">
              {section.fields.map((field) => (
                <QuestionnaireField
                  key={field.id}
                  token={token}
                  docId={doc.id}
                  field={field}
                  value={values[field.id]}
                  onChange={(v) => onFieldChange(field.id, v)}
                  disabled={disabled}
                  submitAttempted={submitAttempted}
                  accent={accent}
                  requestHeaders={requestHeaders}
                />
              ))}
            </div>
          </fieldset>
        ))}
      </div>
    </div>
  );
}

// =====================================================================
// One questionnaire field (typed input per kind, a11y-grouped)
// =====================================================================

interface QuestionnaireFieldProps {
  token: string;
  docId: number;
  field: OnboardingQuestionnaireField;
  value: OnboardingAnswerValue | undefined;
  onChange: (value: OnboardingAnswerValue) => void;
  disabled: boolean;
  submitAttempted: boolean;
  accent: string;
  requestHeaders: () => Record<string, string> | undefined;
}

function QuestionnaireField({
  token,
  docId,
  field,
  value,
  onChange,
  disabled,
  submitAttempted,
  accent,
  requestHeaders,
}: QuestionnaireFieldProps) {
  const fieldDomId = `onb-${docId}-${field.id}`;
  const helpId = field.help ? `${fieldDomId}-help` : undefined;
  const labelText = field.label || field.id;
  const required = !!field.required;

  // PF2: a required field becomes "invalid" once Submit was attempted while it
  // is still unsatisfied; the flag clears live as the user fills it.
  const invalid = submitAttempted && !questionnaireFieldSatisfied(field, value);
  const errorId = invalid ? `${fieldDomId}-error` : undefined;
  // Merge help + error into aria-describedby; aria-errormessage points at the
  // error alone (only valid while aria-invalid is set).
  const describedBy = [helpId, errorId].filter(Boolean).join(' ') || undefined;

  const labelNode = (
    <span className="block text-sm font-medium text-gray-800">
      {labelText}
      {required && (
        <span aria-hidden="true" className="ml-0.5 text-red-600">*</span>
      )}
    </span>
  );
  const help = field.help ? (
    <p id={helpId} className="mt-0.5 text-xs text-gray-500 text-pretty">
      {field.help}
    </p>
  ) : null;
  const errorNode = invalid ? (
    <p id={errorId} role="alert" className="mt-1 text-xs font-medium text-red-700">
      This field is required.
    </p>
  ) : null;

  // --- file upload (upload_request kind / file_upload field) ---
  if (field.kind === 'file_upload') {
    return (
      <FileUploadField
        token={token}
        docId={docId}
        field={field}
        value={value}
        onChange={onChange}
        disabled={disabled}
        accent={accent}
        labelNode={labelNode}
        help={help}
        helpId={helpId}
        invalid={invalid}
        errorId={errorId}
        errorNode={errorNode}
        requestHeaders={requestHeaders}
      />
    );
  }

  // --- choice kinds (radio / checkbox / dropdown) ---
  if (field.kind === 'single_choice' || field.kind === 'multi_choice') {
    return (
      <ChoiceField
        fieldDomId={fieldDomId}
        field={field}
        value={value}
        onChange={onChange}
        disabled={disabled}
        accent={accent}
        labelNode={labelNode}
        help={help}
        helpId={helpId}
        invalid={invalid}
        errorId={errorId}
        errorNode={errorNode}
      />
    );
  }

  // --- text-ish kinds (short_text / paragraph / email / url / date) ---
  const text = typeof value === 'string' ? value : '';
  const onTextChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => onChange(e.target.value);
  const commonInput = {
    id: fieldDomId,
    name: field.id,
    value: text,
    disabled,
    required,
    'aria-required': required,
    'aria-invalid': invalid || undefined,
    'aria-errormessage': errorId,
    maxLength: field.maxLength ?? undefined,
    onChange: onTextChange,
    'aria-describedby': describedBy,
    className:
      'mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder:text-gray-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:bg-gray-100',
    style: { outlineColor: accent } as React.CSSProperties,
  };

  return (
    <div>
      <label htmlFor={fieldDomId}>{labelNode}</label>
      {help}
      {field.kind === 'paragraph' ? (
        <textarea {...commonInput} rows={4} inputMode="text" spellCheck />
      ) : field.kind === 'date' ? (
        <input {...commonInput} type="date" inputMode="numeric" />
      ) : field.kind === 'email' ? (
        <input
          {...commonInput}
          type="email"
          inputMode="email"
          autoComplete="email"
          spellCheck={false}
          placeholder="you@example.com"
        />
      ) : field.kind === 'url' ? (
        <input
          {...commonInput}
          type="url"
          inputMode="url"
          spellCheck={false}
          placeholder="https://example.com..."
        />
      ) : (
        <input {...commonInput} type="text" inputMode="text" />
      )}
      {errorNode}
    </div>
  );
}

// =====================================================================
// Choice field — radio (single) / checkbox (multi) / dropdown
// =====================================================================

interface ChoiceFieldProps {
  fieldDomId: string;
  field: OnboardingQuestionnaireField;
  value: OnboardingAnswerValue | undefined;
  onChange: (value: OnboardingAnswerValue) => void;
  disabled: boolean;
  accent: string;
  labelNode: React.ReactNode;
  help: React.ReactNode;
  helpId?: string;
  invalid?: boolean;
  errorId?: string;
  errorNode?: React.ReactNode;
}

function ChoiceField({
  fieldDomId,
  field,
  value,
  onChange,
  disabled,
  accent,
  labelNode,
  help,
  helpId,
  invalid,
  errorId,
  errorNode,
}: ChoiceFieldProps) {
  const isMulti = field.kind === 'multi_choice';
  const selected = selectedValues(value);
  const other = otherText(value);
  const allowOther = !!field.allow_other;
  const options = field.options ?? [];
  const otherSelected = selected.includes(OTHER_OPTION_TOKEN);
  const describedBy = [helpId, errorId].filter(Boolean).join(' ') || undefined;

  const emitSingle = (optValue: string) => {
    if (optValue === OTHER_OPTION_TOKEN) {
      onChange({ value: OTHER_OPTION_TOKEN, other });
    } else {
      onChange(optValue);
    }
  };

  const emitMulti = (optValue: string, checked: boolean) => {
    const next = checked
      ? [...selected, optValue]
      : selected.filter((v) => v !== optValue);
    if (next.includes(OTHER_OPTION_TOKEN)) {
      onChange({ value: next, other });
    } else {
      onChange(next);
    }
  };

  const emitOtherText = (text: string) => {
    if (isMulti) {
      const next = otherSelected ? selected : [...selected, OTHER_OPTION_TOKEN];
      onChange({ value: next, other: text });
    } else {
      onChange({ value: OTHER_OPTION_TOKEN, other: text });
    }
  };

  // Dropdown display for a single_choice (§7.3 fold).
  if (!isMulti && field.display === 'dropdown') {
    const current = selected[0] ?? '';
    return (
      <div>
        <label htmlFor={fieldDomId}>{labelNode}</label>
        {help}
        <select
          id={fieldDomId}
          name={field.id}
          value={current}
          disabled={disabled}
          required={!!field.required}
          aria-required={!!field.required}
          aria-invalid={invalid || undefined}
          aria-errormessage={errorId}
          aria-describedby={describedBy}
          onChange={(e) => emitSingle(e.target.value)}
          className="mt-1 block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:bg-gray-100"
          style={{ outlineColor: accent }}
        >
          <option value="" disabled>Select…</option>
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
          {allowOther && <option value={OTHER_OPTION_TOKEN}>Other…</option>}
        </select>
        {otherSelected && (
          <OtherWriteIn
            fieldDomId={fieldDomId}
            value={other}
            onChange={emitOtherText}
            disabled={disabled}
            accent={accent}
          />
        )}
        {errorNode}
      </div>
    );
  }

  // Radio (single) / checkbox (multi) group. ``id`` + ``tabIndex={-1}`` make the
  // group focusable so the focus-first-error flow (PF2) can land on it via the
  // shared ``onb-${docId}-${fieldId}`` id; ``aria-required`` announces the
  // requirement to SR users (the visual * is aria-hidden — PF5).
  return (
    <fieldset
      id={fieldDomId}
      tabIndex={-1}
      aria-required={!!field.required}
      aria-invalid={invalid || undefined}
      aria-errormessage={errorId}
      aria-describedby={describedBy}
      className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded"
      style={{ outlineColor: accent }}
    >
      <legend className="text-sm font-medium text-gray-800">{labelNode}</legend>
      {help}
      <div className="mt-2 space-y-1.5">
        {options.map((opt) => {
          const optId = `${fieldDomId}-${opt.value}`;
          const checked = selected.includes(opt.value);
          return (
            <label key={opt.value} htmlFor={optId} className="flex items-center gap-2 text-sm text-gray-700">
              <input
                id={optId}
                type={isMulti ? 'checkbox' : 'radio'}
                name={field.id}
                value={opt.value}
                checked={checked}
                disabled={disabled}
                onChange={(e) =>
                  isMulti
                    ? emitMulti(opt.value, e.target.checked)
                    : emitSingle(opt.value)
                }
                className="h-4 w-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                style={{ accentColor: accent, outlineColor: accent }}
              />
              <span>{opt.label}</span>
            </label>
          );
        })}
        {allowOther && (
          <label
            htmlFor={`${fieldDomId}-other`}
            className="flex items-center gap-2 text-sm text-gray-700"
          >
            <input
              id={`${fieldDomId}-other`}
              type={isMulti ? 'checkbox' : 'radio'}
              name={field.id}
              value={OTHER_OPTION_TOKEN}
              checked={otherSelected}
              disabled={disabled}
              onChange={(e) =>
                isMulti
                  ? emitMulti(OTHER_OPTION_TOKEN, e.target.checked)
                  : emitSingle(OTHER_OPTION_TOKEN)
              }
              className="h-4 w-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              style={{ accentColor: accent, outlineColor: accent }}
            />
            <span>Other</span>
          </label>
        )}
      </div>
      {otherSelected && (
        <OtherWriteIn
          fieldDomId={fieldDomId}
          value={other}
          onChange={emitOtherText}
          disabled={disabled}
          accent={accent}
        />
      )}
      {errorNode}
    </fieldset>
  );
}

function OtherWriteIn({
  fieldDomId,
  value,
  onChange,
  disabled,
  accent,
}: {
  fieldDomId: string;
  value: string;
  onChange: (v: string) => void;
  disabled: boolean;
  accent: string;
}) {
  const id = `${fieldDomId}-other-text`;
  return (
    <div className="mt-2">
      <label htmlFor={id} className="sr-only">Other — please specify</label>
      <input
        id={id}
        type="text"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Please specify..."
        className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder:text-gray-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:bg-gray-100"
        style={{ outlineColor: accent }}
      />
    </div>
  );
}

// =====================================================================
// File upload field (upload_request) — POSTs each file to the P3 endpoint
// =====================================================================

interface FileUploadFieldProps {
  token: string;
  docId: number;
  field: OnboardingQuestionnaireField;
  value: OnboardingAnswerValue | undefined;
  onChange: (value: OnboardingAnswerValue) => void;
  disabled: boolean;
  accent: string;
  labelNode: React.ReactNode;
  help: React.ReactNode;
  helpId?: string;
  invalid?: boolean;
  errorId?: string;
  errorNode?: React.ReactNode;
  requestHeaders: () => Record<string, string> | undefined;
}

/** One uploaded file row as reflected back from the P3 ``/files`` endpoint. */
interface UploadedFile {
  upload_id: number;
  field_id: string;
  original_filename: string;
}

function FileUploadField({
  token,
  docId,
  field,
  value,
  onChange,
  disabled,
  accent,
  labelNode,
  help,
  helpId,
  invalid,
  errorId,
  errorNode,
  requestHeaders,
}: FileUploadFieldProps) {
  const inputId = `onb-file-${docId}-${field.id}`;
  const limitsId = `${inputId}-limits`;
  const maxFiles = field.maxFiles ?? 5;
  const maxMB = field.maxMB ?? 10;

  // The answer for a file_upload field is the list of upload ids; we keep a
  // richer local list (with filenames) for display and reflect the ids back as
  // the draft answer so the completion gate counts them. On (re)load the draft
  // answer carries only the ids — seed the count from them so a reload reflects
  // already-uploaded files; P3's doc payload (``field_uploads`` with names)
  // rehydrates the filenames when wired.
  const [files, setFiles] = useState<UploadedFile[]>(() =>
    (Array.isArray(value) ? value : []).map((id) => ({
      upload_id: Number(id),
      field_id: field.id,
      original_filename: `Uploaded file #${id}`,
    })),
  );
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Reflect the current file ids into the draft answer (the version-fence PATCH
  // ignores these; uploads have their own endpoint, §C.2).
  const reflect = useCallback(
    (next: UploadedFile[]) => {
      setFiles(next);
      onChange(next.map((f) => String(f.upload_id)));
    },
    [onChange],
  );

  const handleSelect = useCallback(
    async (selected: FileList | null) => {
      if (!selected || selected.length === 0) return;
      setError(null);
      const remaining = maxFiles - files.length;
      if (remaining <= 0) {
        setError(`You can upload at most ${maxFiles} file${maxFiles === 1 ? '' : 's'}.`);
        return;
      }
      const toUpload = Array.from(selected).slice(0, remaining);
      setUploading(true);
      const added: UploadedFile[] = [];
      try {
        for (const file of toUpload) {
          if (file.size > maxMB * 1024 * 1024) {
            setError(`"${file.name}" exceeds the ${maxMB} MB limit.`);
            continue;
          }
          const form = new FormData();
          form.append('field_id', field.id);
          form.append('file', file);
          const res = await publicClient.post<UploadedFile>(
            `/api/onboarding/public/${token}/documents/${docId}/files`,
            form,
            { headers: { ...requestHeaders(), 'Content-Type': 'multipart/form-data' } },
          );
          added.push({
            upload_id: res.data.upload_id,
            field_id: res.data.field_id,
            original_filename: res.data.original_filename,
          });
        }
        if (added.length > 0) reflect([...files, ...added]);
      } catch (err) {
        setError(publicErrorMessage(err, 'We could not upload that file. Please try again.'));
      } finally {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = '';
      }
    },
    [field.id, files, maxFiles, maxMB, token, docId, requestHeaders, reflect],
  );

  const removeFile = useCallback(
    async (uploadId: number) => {
      setError(null);
      try {
        await publicClient.delete(
          `/api/onboarding/public/${token}/documents/${docId}/files/${uploadId}`,
          { headers: requestHeaders() },
        );
        reflect(files.filter((f) => f.upload_id !== uploadId));
      } catch (err) {
        setError(publicErrorMessage(err, 'We could not remove that file. Please try again.'));
      }
    },
    [files, token, docId, requestHeaders, reflect],
  );

  const atLimit = files.length >= maxFiles;

  return (
    <div>
      <label htmlFor={inputId}>{labelNode}</label>
      {help}
      <p id={limitsId} className="mt-0.5 text-xs text-gray-500">
        Up to {maxFiles} file{maxFiles === 1 ? '' : 's'}, {maxMB} MB each ·{' '}
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>{files.length}/{maxFiles}</span> uploaded
      </p>
      <input
        ref={fileInputRef}
        id={inputId}
        type="file"
        name={field.id}
        // PF4: native picker hint mirroring the backend allow-list (the server
        // sniff + allow-list stays the authoritative backstop).
        accept={ONBOARDING_UPLOAD_ACCEPT}
        multiple={maxFiles > 1}
        disabled={disabled || uploading || atLimit}
        aria-required={!!field.required}
        aria-invalid={invalid || undefined}
        aria-errormessage={errorId}
        aria-describedby={[helpId, limitsId, errorId].filter(Boolean).join(' ') || undefined}
        onChange={(e) => void handleSelect(e.target.files)}
        className="mt-2 block w-full text-sm text-gray-700 file:mr-3 file:rounded file:border-0 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white disabled:opacity-50"
        style={{ ['--tw-file-bg' as string]: accent } as React.CSSProperties}
      />
      {uploading && (
        <p role="status" aria-live="polite" className="mt-2 inline-flex items-center gap-1 text-xs text-gray-600">
          <ArrowPathIcon className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          Uploading…
        </p>
      )}
      {atLimit && !uploading && (
        // Explain the disabled picker instead of leaving it silently greyed out.
        <p className="mt-2 text-xs text-gray-500">
          Maximum of {maxFiles} file{maxFiles === 1 ? '' : 's'} reached — remove one to add another.
        </p>
      )}
      {error && (
        <p role="alert" aria-live="polite" className="mt-2 text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
          {error}
        </p>
      )}
      {files.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {files.map((f) => (
            <li
              key={f.upload_id}
              className="flex items-center justify-between gap-3 rounded border border-gray-200 bg-white px-3 py-2 text-sm"
            >
              <span className="truncate text-gray-800">{f.original_filename}</span>
              <button
                type="button"
                onClick={() => void removeFile(f.upload_id)}
                disabled={disabled}
                aria-label={`Remove ${f.original_filename}`}
                className="text-xs font-medium text-red-600 hover:text-red-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 rounded disabled:opacity-50"
                style={{ outlineColor: accent }}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      {errorNode}
    </div>
  );
}

// =====================================================================
// Document filler — pdf.js canvas + editable field inputs overlaid
// =====================================================================

interface DocumentFillerProps {
  token: string;
  doc: OnboardingPublicDocument;
  values: Record<string, OnboardingAnswerValue>;
  onFieldChange: (fieldId: string, value: OnboardingAnswerValue) => void;
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
  // This component only renders for an ``esign_pdf`` doc (the FillFlow branches
  // form kinds to QuestionnaireFiller), so its field definitions are the PDF
  // coord list — narrow the union once here for the page/box reads below.
  const esignFields = doc.field_definitions as OnboardingFieldDefinition[];
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
        const firstFieldPage = esignFields[0]?.page;
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
  }, [token, doc.id, esignFields, requestHeaders]);

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
    for (const field of esignFields) {
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
                    value={
                      typeof values[field.id] === 'string'
                        ? (values[field.id] as string)
                        : ''
                    }
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
  const [downloadError, setDownloadError] = useState(false);
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
        // silently indistinguishable from "no documents", and tell the signer
        // explicitly to use their e-mail rather than waiting on a link that
        // failed to load here.
        console.warn('onboarding: in-session download list fetch failed', err);
        if (!cancelled) setDownloadError(true);
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
          {downloadError
            ? 'We couldn’t load your download links here, but your signed copies have been emailed to you. You can safely close this page.'
            : 'Your signed copies will arrive by email shortly. You can safely close this page.'}
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

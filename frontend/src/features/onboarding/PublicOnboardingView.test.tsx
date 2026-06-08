/**
 * Behavioural tests for the v3 questionnaire renderer on the public fill page.
 *
 * The network boundary is the bare ``axios`` instance the page creates and the
 * pdf.js / SignatureCanvas render pipeline — both mocked (the only externals).
 * Everything else (the widened ``draftValues`` typing, the choice/Other write-in
 * answer shape, the debounced autosave under version drift, the ``POST /viewed``
 * on first render, the ``beforeunload`` guard, and the a11y fieldset/legend
 * groups) is the component's own logic and is exercised for real.
 */
import {
  describe,
  it,
  expect,
  vi,
  beforeEach,
  beforeAll,
  afterEach,
} from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

// --- Mock the bare axios instance the page creates -------------------------
// The page calls ``axios.create(...)`` and uses .get/.post/.patch/.delete on
// that instance. ``vi.hoisted`` lets the (hoisted) ``vi.mock`` factory close over
// the same controllable fake instance each test programs.
const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));
vi.mock('axios', () => ({
  default: { create: vi.fn(() => api) },
}));

// pdf.js + its worker (never exercised on a questionnaire doc, but the module
// is imported at the top of the page).
vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: {},
  getDocument: vi.fn(() => ({ promise: Promise.resolve({ numPages: 1, getPage: vi.fn(), destroy: vi.fn() }), destroy: vi.fn() })),
}));
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: 'worker.js' }));

// SignatureCanvas reaches for a real <canvas>; not needed for questionnaire.
vi.mock('../../components/SignatureCanvas', () => ({
  SignatureCanvas: () => null,
}));

import PublicOnboardingView from './PublicOnboardingView';
import { ONBOARDING_UPLOAD_ACCEPT } from './uploadConstants';
import type { OnboardingPublicDocument } from '../../types';

const TOKEN = 'tok-abc';

function questionnaireDoc(
  overrides: Partial<OnboardingPublicDocument> = {},
): OnboardingPublicDocument {
  return {
    id: 7,
    kind: 'questionnaire',
    original_filename: 'Client Strategy Insights',
    field_values: {},
    field_values_version: 0,
    requires_esign: false,
    field_definitions: [
      {
        id: 'client_name',
        kind: 'short_text',
        label: 'Client Name',
        required: true,
        section_id: 'basics',
        section_label: 'Basics',
      },
      {
        id: 'channels',
        kind: 'multi_choice',
        label: 'Channels used',
        required: true,
        allow_other: true,
        section_id: 'marketing',
        section_label: 'Marketing',
        options: [
          { value: 'seo', label: 'SEO' },
          { value: 'ppc', label: 'Paid Ads' },
        ],
      },
    ],
    ...overrides,
  } as OnboardingPublicDocument;
}

function preGatePayload() {
  return {
    status: 'active',
    document_count: 1,
    requires_email_verification: true,
    status_message: null,
    branding: null,
  };
}

function postGatePayload(doc: OnboardingPublicDocument) {
  return {
    status: 'in_progress',
    document_count: 1,
    status_message: null,
    branding: null,
    documents: [doc],
    signature_version: 0,
    has_signature: false,
    has_consented: false,
    esign_disclosure: null,
    esign_disclosure_version: null,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/onboarding/${TOKEN}`]}>
      <Routes>
        <Route path="/onboarding/:token" element={<PublicOnboardingView />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Drive the email gate so the post-gate questionnaire renders. The page calls
 * GET (pre-gate) → POST /verify → GET (post-gate). */
async function unlockGate(doc: OnboardingPublicDocument) {
  const user = userEvent.setup();
  api.get
    .mockResolvedValueOnce({ data: preGatePayload() }) // initial pre-gate load
    .mockResolvedValue({ data: postGatePayload(doc) }); // every subsequent load
  api.post.mockImplementation((url: string) => {
    if (url.endsWith('/verify')) {
      return Promise.resolve({ data: { success: true, session_token: 's-tok', expires_in: 600 } });
    }
    if (url.endsWith('/viewed')) return Promise.resolve({ data: { viewed: true, opened: true } });
    return Promise.resolve({ data: {} });
  });
  api.patch.mockResolvedValue({ data: { field_values_version: 1 } });

  renderPage();
  await waitFor(() => expect(api.get).toHaveBeenCalled());
  const emailInput = await screen.findByLabelText(/email address/i);
  await user.type(emailInput, 'client@example.com');
  await user.click(screen.getByRole('button', { name: /continue/i }));
  await screen.findByText(doc.original_filename);
  return user;
}

beforeAll(() => {
  // jsdom: stub the bits the page touches but jsdom lacks.
  // matchMedia (prefers-reduced-motion / useForceLightMode).
  window.matchMedia = window.matchMedia || ((q: string) => ({
    matches: false, media: q, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
  } as unknown as MediaQueryList));
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
  sessionStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('PublicOnboardingView — questionnaire renderer', () => {
  it('renders a real form (not the pdf.js canvas) with a11y section groups', async () => {
    await unlockGate(questionnaireDoc());

    // Sections render as fieldset/legend groups (a11y-mandated).
    expect(screen.getByText('Basics')).toBeInTheDocument();
    expect(screen.getByText('Marketing')).toBeInTheDocument();

    // The text field is a labelled input.
    const nameInput = screen.getByLabelText(/Client Name/i);
    expect(nameInput).toHaveAttribute('name', 'client_name');

    // The multi_choice renders a checkbox group with real <label htmlFor>.
    const seo = screen.getByLabelText('SEO');
    expect(seo).toHaveAttribute('type', 'checkbox');
    expect(screen.getByLabelText('Paid Ads')).toBeInTheDocument();
    // allow_other adds an "Other" checkbox.
    expect(screen.getByLabelText('Other')).toBeInTheDocument();

    // pdf.js is never invoked for a questionnaire doc.
    const pdfjs = await import('pdfjs-dist');
    expect(pdfjs.getDocument).not.toHaveBeenCalled();
  });

  it('POSTs /viewed on first render of a questionnaire doc', async () => {
    await unlockGate(questionnaireDoc());
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        `/api/onboarding/public/${TOKEN}/documents/7/viewed`,
        {},
        expect.anything(),
      ),
    );
    // Idempotent guard: not POSTed twice for the same doc.
    const viewedCalls = api.post.mock.calls.filter((c) => String(c[0]).endsWith('/viewed'));
    expect(viewedCalls.length).toBe(1);
  });

  it('stores the multi-select Other write-in as the {value, other} shape', async () => {
    const user = await unlockGate(questionnaireDoc());

    await user.click(screen.getByLabelText('SEO'));
    await user.click(screen.getByLabelText('Other'));
    const otherInput = await screen.findByLabelText(/Other — please specify/i);
    await user.type(otherInput, 'TikTok');

    // The debounced autosave (1200ms) PATCHes the {value, other} shape.
    await waitFor(
      () => {
        const patch = api.patch.mock.calls.at(-1);
        expect(patch).toBeTruthy();
        const body = patch![1] as { field_values: Record<string, unknown> };
        expect(body.field_values.channels).toEqual({
          value: ['seo', '__other__'],
          other: 'TikTok',
        });
      },
      { timeout: 3000 },
    );
  });

  it('autosaves a typed answer and reconciles on a 409 version drift', async () => {
    const user = await unlockGate(questionnaireDoc());

    // First autosave 409s (version drifted) → the page refetches.
    api.patch
      .mockRejectedValueOnce({ response: { status: 409 } })
      .mockResolvedValue({ data: { field_values_version: 2 } });
    api.get.mockResolvedValue({
      data: postGatePayload(questionnaireDoc({ field_values_version: 2 })),
    });

    await user.type(screen.getByLabelText(/Client Name/i), 'Jane');

    await waitFor(
      () => expect(api.patch).toHaveBeenCalled(),
      { timeout: 3000 },
    );
    // The 409 path surfaces the "updated elsewhere" notice and refetches.
    await waitFor(() =>
      expect(screen.getByText(/updated elsewhere/i)).toBeInTheDocument(),
    );
  });

  it('arms a beforeunload guard once an answer is dirty', async () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    const user = await unlockGate(questionnaireDoc());

    // No beforeunload listener before any edit.
    expect(addSpy.mock.calls.some((c) => c[0] === 'beforeunload')).toBe(false);

    await user.type(screen.getByLabelText(/Client Name/i), 'J');
    await waitFor(() =>
      expect(addSpy.mock.calls.some((c) => c[0] === 'beforeunload')).toBe(true),
    );
    addSpy.mockRestore();
  });

  it('renders a single_choice dropdown when display="dropdown"', async () => {
    const doc = questionnaireDoc({
      field_definitions: [
        {
          id: 'size',
          kind: 'single_choice',
          label: 'Business Size',
          required: true,
          display: 'dropdown',
          options: [
            { value: '2-10', label: '2-10' },
            { value: '11-50', label: '11-50' },
          ],
        },
      ],
    } as Partial<OnboardingPublicDocument>);
    const user = await unlockGate(doc);

    const select = screen.getByLabelText(/Business Size/i);
    expect(select.tagName).toBe('SELECT');
    await user.selectOptions(select, '11-50');
    await waitFor(
      () => {
        const patch = api.patch.mock.calls.at(-1);
        const body = patch![1] as { field_values: Record<string, unknown> };
        expect(body.field_values.size).toBe('11-50');
      },
      { timeout: 3000 },
    );
  });

  // BUG 1 — file_upload answers must NOT ride the version-fence PATCH; the
  // /files endpoint is the sole server-side writer. Sending the reflected ids
  // would 422 (the backend expects int upload-row ids) and block completion.
  it('excludes file_upload fields from the PATCH body (uploads bypass the fence)', async () => {
    const doc = questionnaireDoc({
      kind: 'upload_request',
      original_filename: 'Branding Documentation',
      field_definitions: [
        {
          id: 'notes',
          kind: 'short_text',
          label: 'Notes',
          required: false,
          section_id: 's',
          section_label: 'Assets',
        },
        {
          id: 'logos',
          kind: 'file_upload',
          label: 'Upload logos',
          required: true,
          maxFiles: 3,
          maxMB: 10,
          section_id: 's',
          section_label: 'Assets',
        },
      ],
    } as Partial<OnboardingPublicDocument>);
    const user = await unlockGate(doc);

    // Upload a file → the /files POST reflects an upload id into the draft.
    api.post.mockImplementation((url: string) => {
      if (url.endsWith('/verify')) {
        return Promise.resolve({ data: { success: true, session_token: 's-tok', expires_in: 600 } });
      }
      if (url.endsWith('/viewed')) return Promise.resolve({ data: { viewed: true, opened: true } });
      if (url.endsWith('/files')) {
        return Promise.resolve({
          data: { upload_id: 42, field_id: 'logos', original_filename: 'logo.png' },
        });
      }
      return Promise.resolve({ data: {} });
    });
    const fileInput = screen.getByLabelText(/Upload logos/i);
    const file = new File([new Uint8Array([1, 2, 3])], 'logo.png', { type: 'image/png' });
    await user.upload(fileInput, file);
    await waitFor(() =>
      expect(api.post.mock.calls.some((c) => String(c[0]).endsWith('/files'))).toBe(true),
    );

    // Now type the text field → the autosave PATCH must carry ``notes`` but NOT
    // ``logos`` (the uploaded file field is stripped).
    await user.type(screen.getByLabelText(/Notes/i), 'hi');
    await waitFor(
      () => {
        const patch = api.patch.mock.calls.at(-1);
        expect(patch).toBeTruthy();
        const body = patch![1] as { field_values: Record<string, unknown> };
        expect(body.field_values).toHaveProperty('notes', 'hi');
        expect(body.field_values).not.toHaveProperty('logos');
      },
      { timeout: 3000 },
    );
  });

  // BUG 3 — a sensitive required field stores None server-side, so a 409-refetch
  // reseed must not permanently block Submit (the server holds the ciphertext).
  it('a sensitive required field does not block submit after a reseed', async () => {
    const doc = questionnaireDoc({
      field_definitions: [
        {
          id: 'pw',
          kind: 'short_text',
          label: 'Hosting Password',
          required: true,
          sensitive: true,
          section_id: 's',
          section_label: 'Credentials',
        },
      ],
    } as Partial<OnboardingPublicDocument>);
    // Server reseeds field_values with NO pw value (sensitive → stored as None).
    await unlockGate(doc);

    // The single doc is viewed; with the sensitive field treated as satisfied,
    // the Submit button is enabled (not blocked by the empty local value).
    const submit = await screen.findByRole('button', { name: /submit documents/i });
    await waitFor(() => expect(submit).toBeEnabled());
    // The "complete the required fields" blocker must NOT mention the sensitive field.
    expect(screen.queryByText(/Hosting Password/i, { selector: 'li' })).toBeNull();
  });
});

// =====================================================================
// Final-gate fixes — PF1 (focus theft), PF2 (focus-first-error + a11y),
// PF4 (accept), PF5 (aria-required), PF6 (submit stays enabled).
// =====================================================================

describe('PublicOnboardingView — final-gate accessibility + autosave fixes', () => {
  beforeAll(() => {
    // jsdom doesn't implement scrollIntoView; the focus-first-error flow calls
    // it. Stub it so the real component code runs unchanged.
    Element.prototype.scrollIntoView = vi.fn();
  });

  it('PF1: keeps inputs enabled + focused during autosave (no focus theft)', async () => {
    const user = await unlockGate(questionnaireDoc());

    // Make the autosave PATCH hang so ``savingDoc`` stays true deterministically.
    let release: () => void = () => {};
    api.patch.mockImplementation(
      () =>
        new Promise((res) => {
          release = () => res({ data: { field_values_version: 1 } });
        }),
    );

    const input = screen.getByLabelText(/Client Name/i);
    await user.type(input, 'Jane');

    // Debounced autosave (1200ms) fires → savingDoc=true → passive "Saving…".
    await screen.findByText(/saving…/i, {}, { timeout: 3000 });

    // The bug: a disabled fieldset would blur the input to <body>. Fixed: the
    // input stays enabled AND keeps focus while the save is in flight.
    expect(input).toBeEnabled();
    expect(document.activeElement).toBe(input);

    release();
  });

  it('PF2/PF6: submit stays enabled; click focuses first missing field + aria-invalid', async () => {
    const user = await unlockGate(questionnaireDoc()); // client_name + channels required

    const submit = await screen.findByRole('button', { name: /submit documents/i });
    // PF6: enabled even though the form is incomplete.
    expect(submit).toBeEnabled();

    await user.click(submit);

    // PF2: the first unsatisfied required field is focused + marked invalid.
    const nameInput = screen.getByLabelText(/Client Name/i);
    expect(nameInput).toHaveAttribute('aria-invalid', 'true');
    expect(document.activeElement).toBe(nameInput);

    // Inline per-field error is rendered and wired via aria-errormessage. (Both
    // required fields are flagged after submit, so scope to THIS field's error.)
    const errId = nameInput.getAttribute('aria-errormessage');
    expect(errId).toBeTruthy();
    const err = document.getElementById(errId as string);
    expect(err).toHaveTextContent(/this field is required/i);

    // Validate-first: no /complete request was made.
    expect(
      api.post.mock.calls.some((c) => String(c[0]).endsWith('/complete')),
    ).toBe(false);

    // The error clears live once the field is filled.
    await user.type(nameInput, 'Jane');
    await waitFor(() =>
      expect(nameInput).not.toHaveAttribute('aria-invalid', 'true'),
    );
  });

  it('PF4: the file input carries the shared accept allow-list', async () => {
    const doc = questionnaireDoc({
      kind: 'upload_request',
      original_filename: 'Brand Assets',
      field_definitions: [
        {
          id: 'logos',
          kind: 'file_upload',
          label: 'Upload logos',
          required: true,
          maxFiles: 3,
          maxMB: 10,
        },
      ],
    } as Partial<OnboardingPublicDocument>);
    await unlockGate(doc);

    const fileInput = screen.getByLabelText(/Upload logos/i);
    expect(fileInput).toHaveAttribute('accept', ONBOARDING_UPLOAD_ACCEPT);
    const accept = fileInput.getAttribute('accept') ?? '';
    expect(accept).toContain('.pdf');
    expect(accept).toContain('application/pdf');
    expect(accept).not.toContain('.svg');
  });

  it('PF5: required choice / dropdown / file controls are aria-required', async () => {
    const doc = questionnaireDoc({
      kind: 'upload_request',
      original_filename: 'Mixed',
      field_definitions: [
        {
          id: 'pick',
          kind: 'single_choice',
          label: 'Pick one',
          required: true,
          options: [{ value: 'a', label: 'A' }],
        },
        {
          id: 'drop',
          kind: 'single_choice',
          label: 'Drop one',
          required: true,
          display: 'dropdown',
          options: [{ value: 'x', label: 'X' }],
        },
        {
          id: 'up',
          kind: 'file_upload',
          label: 'Upload file',
          required: true,
          maxFiles: 1,
          maxMB: 5,
        },
      ],
    } as Partial<OnboardingPublicDocument>);
    await unlockGate(doc);

    // Radio group <fieldset> (the visual * is aria-hidden, so SR users rely on this).
    const radioGroup = screen.getByRole('group', { name: /Pick one/i });
    expect(radioGroup).toHaveAttribute('aria-required', 'true');
    // Dropdown <select>.
    expect(screen.getByLabelText(/Drop one/i)).toHaveAttribute('aria-required', 'true');
    // File <input>.
    expect(screen.getByLabelText(/Upload file/i)).toHaveAttribute('aria-required', 'true');
  });
});

describe('PublicOnboardingView — session persistence + expiry (QOL)', () => {
  const SESSION_KEY = `onboardingSession:v1:${TOKEN}`;
  const DOCINDEX_KEY = `onboardingDocIndex:v1:${TOKEN}`;

  it('caches the session token + position in sessionStorage after verify', async () => {
    await unlockGate(questionnaireDoc());
    expect(sessionStorage.getItem(SESSION_KEY)).toBe('s-tok');
    expect(sessionStorage.getItem(DOCINDEX_KEY)).toBe('0');
  });

  it('skips the e-mail gate on reload when a cached session is present', async () => {
    sessionStorage.setItem(SESSION_KEY, 's-tok');
    const doc = questionnaireDoc();
    // The very first GET carries the cached session → returns post-gate docs.
    api.get.mockResolvedValue({ data: postGatePayload(doc) });
    api.post.mockResolvedValue({ data: { viewed: true, opened: true } });
    api.patch.mockResolvedValue({ data: { field_values_version: 1 } });

    renderPage();

    // The form renders WITHOUT ever typing an e-mail — the gate was skipped.
    await screen.findByText(doc.original_filename);
    expect(screen.queryByLabelText(/email address/i)).not.toBeInTheDocument();
    // …and that first GET carried the session header.
    expect(api.get).toHaveBeenCalledWith(
      expect.stringContaining(`/public/${TOKEN}`),
      expect.objectContaining({
        headers: { 'X-Onboarding-Session': 's-tok' },
      }),
    );
  });

  it('drops an expired cached session back to the gate with a notice (401)', async () => {
    sessionStorage.setItem(SESSION_KEY, 'stale-tok');
    // First GET (with the stale session) → 401; the re-fetch (no session) loads
    // the pre-gate payload so the branded gate can render.
    api.get
      .mockRejectedValueOnce({ response: { status: 401 } })
      .mockResolvedValue({ data: preGatePayload() });

    renderPage();

    // The reassuring timeout notice shows and we're back on the e-mail gate…
    expect(await screen.findByText(/timed out/i)).toBeInTheDocument();
    expect(await screen.findByLabelText(/email address/i)).toBeInTheDocument();
    // …and the stale token was purged.
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull();
  });

  it('clears the cached session + position on completion', async () => {
    const doc = questionnaireDoc({ field_definitions: [], requires_esign: false });
    sessionStorage.setItem(SESSION_KEY, 's-tok');
    sessionStorage.setItem(DOCINDEX_KEY, '0');
    // A packet already in the completed state seeds completed=true on load.
    api.get.mockResolvedValue({
      data: { ...postGatePayload(doc), status: 'completed' },
    });
    api.post.mockResolvedValue({ data: {} });

    renderPage();

    await screen.findByText(/all done/i);
    await waitFor(() => expect(sessionStorage.getItem(SESSION_KEY)).toBeNull());
    expect(sessionStorage.getItem(DOCINDEX_KEY)).toBeNull();
  });
});

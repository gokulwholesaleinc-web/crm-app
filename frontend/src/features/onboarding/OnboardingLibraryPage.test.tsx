/**
 * Behavioural tests for the onboarding template library page.
 *
 * The network boundary — ``apiClient`` (the shared axios-ish client) — is
 * mocked, and so is the ``utils/toast`` sink (it just wraps react-hot-toast,
 * which has no <Toaster> in the test tree) so user-facing messages can be
 * asserted. The real ``api/onboarding`` wrappers, React Query mutations, and
 * the page's own handlers all run for real. Behaviours pinned:
 *
 *  - New Template: opens the code-split "Create template" wizard (stubbed here;
 *    its commit/validation behaviour is covered by OnboardingTemplateWizard.test).
 *  - #13 (edit metadata): the "Edit details" control PATCHes name /
 *    service_tag / requires_esign through ``updateOnboardingTemplate``.
 *  - #11 (retired): a retired row hides edit actions and offers Restore,
 *    which POSTs to the restore endpoint and refetches the list.
 *  - C2 / #2 / #11 (409 field-save): the field-save PATCH can 409 for EITHER
 *    a replaced PDF or a retired template; the page surfaces the server's
 *    detail verbatim and closes + refetches — owned by the library page, not
 *    the editor.
 *
 * The pdf.js editor is heavy and irrelevant to these flows, so the lazily
 * imported ``OnboardingTemplateEditor`` is replaced with a tiny stub that just
 * exposes a "Save fields" button wired to the real ``onSave`` the page passes.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  renderWithProviders,
  screen,
  waitFor,
  fireEvent,
} from '../../test-utils/renderWithProviders';
import { useAuthStore } from '../../store/authStore';
import type { OnboardingTemplate } from '../../types';

// --- Network boundary: mock apiClient only --------------------------------
const apiClientMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));
vi.mock('../../api/client', () => ({
  apiClient: apiClientMock,
  // authStore re-exports this at module init; the mock must satisfy every
  // named export its consumers touch.
  registerAuthTokenGetter: vi.fn(),
}));

// Toast sink: wraps react-hot-toast, which has no <Toaster> in the test tree.
// Mock it so the messages the page surfaces can be asserted directly.
vi.mock('../../utils/toast', () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

// The real editor pulls in pdf.js (jsdom can't render it) and is code-split.
// Swap it for a stub that calls back into the page's real ``onSave`` so the
// 409 handling on the parent is exercised without the canvas machinery.
vi.mock('./OnboardingTemplateEditor', () => ({
  default: ({
    isOpen,
    onSave,
  }: {
    isOpen: boolean;
    onSave: (fields: never[]) => Promise<void>;
  }) =>
    isOpen ? (
      <div data-testid="editor-stub">
        <button type="button" onClick={() => void onSave([])}>
          Stub save fields
        </button>
      </div>
    ) : null,
}));

// The create wizard is heavy (pdf.js + both builders) and code-split. Stub it
// so this page test verifies only the wire-in (New Template → wizard mounted);
// the wizard's own commit/validation behaviour is covered by its dedicated test.
vi.mock('./OnboardingTemplateWizard', () => ({
  default: ({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div data-testid="wizard-stub">Create wizard</div> : null,
}));

// URL.createObjectURL / revokeObjectURL aren't in jsdom; the page calls them
// when opening/closing the editor.
beforeEach(() => {
  vi.clearAllMocks();
  URL.createObjectURL = vi.fn(() => 'blob:stub');
  URL.revokeObjectURL = vi.fn();
  // Flip the real auth store to authenticated so useAuthQuery's gate opens.
  useAuthStore.setState({
    isAuthenticated: true,
    isLoading: false,
    token: 'test-token',
  });
});

import OnboardingLibraryPage from './OnboardingLibraryPage';
import { showError } from '../../utils/toast';

function makeTemplate(over: Partial<OnboardingTemplate> = {}): OnboardingTemplate {
  return {
    id: 7,
    name: 'New client intake',
    description: 'Standard packet',
    service_tag: null,
    owner_id: null,
    has_pdf: true,
    pdf_version: 3,
    field_definitions: [
      {
        id: 'ein',
        kind: 'text',
        label: 'EIN',
        description: '',
        required: false,
        prefill: null,
        page: 1,
        x: 10,
        y: 10,
        w: 100,
        h: 20,
      },
    ],
    requires_esign: false,
    is_active: true,
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-02T00:00:00Z',
    ...over,
  };
}

/** Queue the initial list GET (and any refetch) for a single template. */
function queueList(template: OnboardingTemplate) {
  apiClientMock.get.mockResolvedValue({ data: [template] });
}

describe('OnboardingLibraryPage — New Template opens the wizard', () => {
  it('mounts the create-template wizard only after New Template is clicked', async () => {
    const template = makeTemplate();
    queueList(template);

    renderWithProviders(<OnboardingLibraryPage />);
    await screen.findByText('New client intake');

    // The wizard is not mounted until the user opens it.
    expect(screen.queryByTestId('wizard-stub')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /new template/i }));

    // Clicking New Template lazy-loads + mounts the wizard (isOpen).
    expect(await screen.findByTestId('wizard-stub')).toBeInTheDocument();
  });
});

describe('OnboardingLibraryPage — #13 edit metadata', () => {
  it('PATCHes name / service_tag / requires_esign via updateOnboardingTemplate', async () => {
    const template = makeTemplate();
    queueList(template);
    apiClientMock.patch.mockResolvedValue({
      data: makeTemplate({ name: 'Renamed packet', service_tag: 'tax', requires_esign: true }),
    });

    renderWithProviders(<OnboardingLibraryPage />);
    await screen.findByText('New client intake');

    // Open the edit-details modal.
    fireEvent.click(screen.getByRole('button', { name: /edit details/i }));

    const nameInput = await screen.findByLabelText('Name');
    expect(nameInput).toHaveValue('New client intake');

    fireEvent.change(nameInput, { target: { value: 'Renamed packet' } });
    fireEvent.change(screen.getByLabelText('Service tag (optional)'), {
      target: { value: 'tax' },
    });
    fireEvent.click(screen.getByLabelText(/requires e-signature/i));

    fireEvent.click(screen.getByRole('button', { name: 'Save details' }));

    await waitFor(() => expect(apiClientMock.patch).toHaveBeenCalledTimes(1));
    const [url, body] = apiClientMock.patch.mock.calls[0]!;
    expect(url).toBe('/api/onboarding/templates/7');
    expect(body).toMatchObject({
      name: 'Renamed packet',
      service_tag: 'tax',
      requires_esign: true,
    });
    // Metadata edits must NOT smuggle field_definitions / pdf_version.
    expect(body).not.toHaveProperty('field_definitions');
    expect(body).not.toHaveProperty('pdf_version');
  });
});

describe('OnboardingLibraryPage — C2 / #2 / #11 409 field-save', () => {
  it('surfaces the server detail verbatim and closes the editor when the field-save 409s', async () => {
    const template = makeTemplate();
    queueList(template);
    // The field-save PATCH can 409 for EITHER a replaced PDF (#2) or a retired
    // template (#11). The handler must surface whatever the server says — here
    // the "retired" variant, to prove no hardcoded "PDF replaced" message.
    const serverDetail = 'Template is retired and cannot be edited.';
    apiClientMock.patch.mockRejectedValue({ status_code: 409, detail: serverDetail });
    // Opening the editor downloads the PDF blob.
    apiClientMock.get.mockImplementation((url: string) => {
      if (url.endsWith('/pdf')) return Promise.resolve({ data: new Blob() });
      return Promise.resolve({ data: [template] });
    });

    renderWithProviders(<OnboardingLibraryPage />);
    await screen.findByText('New client intake');

    // Open the (stubbed) field editor.
    fireEvent.click(screen.getByRole('button', { name: /edit fields/i }));
    await screen.findByTestId('editor-stub');

    // Trigger the field-save → 409.
    fireEvent.click(screen.getByRole('button', { name: 'Stub save fields' }));

    // PATCH was sent with the captured pdf_version as the optimistic-lock token.
    await waitFor(() => expect(apiClientMock.patch).toHaveBeenCalledTimes(1));
    const [url, body] = apiClientMock.patch.mock.calls[0]!;
    expect(url).toBe('/api/onboarding/templates/7');
    expect(body).toMatchObject({ pdf_version: 3 });
    expect(body).toHaveProperty('field_definitions');

    // The server's detail is surfaced verbatim — not a hardcoded message.
    await waitFor(() => expect(showError).toHaveBeenCalledWith(serverDetail));

    // The editor closes (refetch) so the user reopens against current state.
    await waitFor(() => expect(screen.queryByTestId('editor-stub')).not.toBeInTheDocument());
  });
});

describe('OnboardingLibraryPage — #11 restore retired template', () => {
  it('hides edit actions, offers Restore, and POSTs to the restore endpoint then refetches', async () => {
    const retired = makeTemplate({ is_active: false });
    // Initial list (include_inactive surfaces the retired row) + the refetch
    // after restore returns the now-active template.
    apiClientMock.get
      .mockResolvedValueOnce({ data: [retired] })
      .mockResolvedValue({ data: [makeTemplate({ is_active: true })] });
    apiClientMock.post.mockResolvedValue({ data: makeTemplate({ is_active: true }) });

    renderWithProviders(<OnboardingLibraryPage />);
    await screen.findByText('New client intake');

    // Retired rows hide every edit action — they'd all 409 server-side.
    expect(screen.queryByRole('button', { name: /edit fields/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /edit details/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /retire/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /upload pdf|replace pdf/i })).not.toBeInTheDocument();

    // Restore POSTs to the restore endpoint.
    fireEvent.click(screen.getByRole('button', { name: /restore/i }));
    await waitFor(() => expect(apiClientMock.post).toHaveBeenCalledTimes(1));
    expect(apiClientMock.post.mock.calls[0]![0]).toBe('/api/onboarding/templates/7/restore');

    // On success the list is invalidated → refetched (the GET fires again).
    await waitFor(() => expect(apiClientMock.get.mock.calls.length).toBeGreaterThan(1));
  });
});

describe('OnboardingLibraryPage — Copy action (clone)', () => {
  it('shows Copy only on active questionnaire/upload rows, never e-sign or retired', async () => {
    // A mixed list: an active questionnaire (copyable), an active e-sign (not —
    // its PDF + fields are template-specific), and a retired questionnaire (not —
    // retired rows offer only Restore).
    apiClientMock.get.mockResolvedValue({
      data: [
        makeTemplate({ id: 7, name: 'Intake Questionnaire', kind: 'questionnaire', has_pdf: false }),
        makeTemplate({ id: 8, name: 'Signed Agreement', kind: 'esign_pdf', has_pdf: true }),
        makeTemplate({ id: 9, name: 'Old Questionnaire', kind: 'questionnaire', has_pdf: false, is_active: false }),
      ],
    });

    renderWithProviders(<OnboardingLibraryPage />);
    await screen.findByText('Intake Questionnaire');

    // Exactly one Copy button — the active questionnaire's.
    const copyButtons = screen.getAllByRole('button', { name: 'Copy' });
    expect(copyButtons).toHaveLength(1);

    // Clicking it clones via the clone endpoint.
    apiClientMock.post.mockResolvedValue({
      data: makeTemplate({ id: 12, name: 'Intake Questionnaire (copy)' }),
    });
    fireEvent.click(copyButtons[0]!);
    await waitFor(() => expect(apiClientMock.post).toHaveBeenCalledTimes(1));
    expect(apiClientMock.post.mock.calls[0]![0]).toBe('/api/onboarding/templates/7/clone');
  });
});

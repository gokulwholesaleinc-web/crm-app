/**
 * Behavioural tests for the "Create Onboarding Template" wizard.
 *
 * The api/onboarding HTTP boundary is mocked (the established FE pattern); the
 * wizard's real step/validation/commit wiring runs. pdf.js is mocked for the
 * pre-check, and the e-sign editor body is stubbed (the canvas drag-placement is
 * exercised by OnboardingTemplateEditor.test) with a button that injects a
 * signature field so the 3-call commit sequence can be asserted.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  renderWithProviders,
  screen,
  waitFor,
  fireEvent,
} from '../../test-utils/renderWithProviders';

const apiMock = vi.hoisted(() => ({
  createOnboardingTemplate: vi.fn(),
  uploadOnboardingTemplatePdf: vi.fn(),
  updateOnboardingTemplate: vi.fn(),
  listOnboardingTemplates: vi.fn(),
  retireOnboardingTemplate: vi.fn(),
  restoreOnboardingTemplate: vi.fn(),
  ONBOARDING_PDF_MAX_BYTES: 25 * 1024 * 1024,
}));
vi.mock('../../api/onboarding', () => apiMock);
vi.mock('../../utils/toast', () => ({ showSuccess: vi.fn(), showError: vi.fn() }));

// pdf.js — the wizard only calls getDocument for the pre-check.
vi.mock('pdfjs-dist', () => ({
  getDocument: vi.fn(() => ({
    promise: Promise.resolve({
      numPages: 1,
      getPage: () => Promise.resolve({ rotate: 0 }),
      destroy: vi.fn(),
    }),
  })),
}));

// Stub the e-sign editor body: a button that injects a valid signature field so
// the commit can be reached without the real canvas.
vi.mock('./OnboardingTemplateEditor', () => ({
  OnboardingTemplateEditorBody: ({
    value,
    onChange,
  }: {
    value: unknown[];
    onChange: (fields: unknown[]) => void;
  }) => (
    <div data-testid="esign-editor-stub">
      <span data-testid="esign-field-count">{value.length}</span>
      <button
        type="button"
        onClick={() =>
          onChange([
            ...value,
            {
              id: 'signature_1',
              kind: 'signature',
              label: 'Sign here',
              required: true,
              prefill: null,
              page: 1,
              x: 10,
              y: 10,
              w: 100,
              h: 40,
            },
          ])
        }
      >
        stub place signature
      </button>
    </div>
  ),
}));

import { OnboardingTemplateWizard } from './OnboardingTemplateWizard';
import { showSuccess } from '../../utils/toast';

beforeEach(() => {
  vi.clearAllMocks();
  URL.createObjectURL = vi.fn(() => 'blob:stub');
  URL.revokeObjectURL = vi.fn();
  apiMock.listOnboardingTemplates.mockResolvedValue([]);
});

function renderWizard() {
  const onClose = vi.fn();
  const onCreated = vi.fn();
  renderWithProviders(
    <OnboardingTemplateWizard isOpen onClose={onClose} onCreated={onCreated} />,
  );
  return { onClose, onCreated };
}

/** Select a kind on the Kind step and advance to Basics. */
function chooseKind(name: RegExp) {
  fireEvent.click(screen.getByRole('radio', { name }));
  fireEvent.click(screen.getByRole('button', { name: /next: basics/i }));
}

describe('OnboardingTemplateWizard — questionnaire (single create-with-fields)', () => {
  it('creates a questionnaire in ONE call with cleaned fields and OMITS a blank service_tag', async () => {
    apiMock.createOnboardingTemplate.mockResolvedValue({ id: 9, name: 'Intake' });
    const { onClose, onCreated } = renderWizard();

    chooseKind(/questionnaire/i);
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Intake' } });
    fireEvent.click(screen.getByRole('button', { name: /next: build/i }));

    // Add one question + give it a label.
    fireEvent.click(screen.getByRole('button', { name: /add question/i }));
    fireEvent.change(screen.getByLabelText('Question'), {
      target: { value: 'Company name' },
    });

    fireEvent.click(screen.getByRole('button', { name: /next: review/i }));
    fireEvent.click(screen.getByRole('button', { name: /create template/i }));

    await waitFor(() => expect(apiMock.createOnboardingTemplate).toHaveBeenCalledTimes(1));
    const payload = apiMock.createOnboardingTemplate.mock.calls[0]![0];
    expect(payload).toMatchObject({
      name: 'Intake',
      kind: 'questionnaire',
      field_definitions: [
        { id: expect.any(String), kind: 'short_text', label: 'Company name', required: false },
      ],
    });
    // Blank service tag → the key is OMITTED entirely (never sent as "").
    expect(payload).not.toHaveProperty('service_tag');
    // Single call — no upload/PATCH for a form kind.
    expect(apiMock.uploadOnboardingTemplatePdf).not.toHaveBeenCalled();
    expect(apiMock.updateOnboardingTemplate).not.toHaveBeenCalled();

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(showSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it('sends service_tag when provided', async () => {
    apiMock.createOnboardingTemplate.mockResolvedValue({ id: 9, name: 'Intake' });
    renderWizard();

    chooseKind(/questionnaire/i);
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Intake' } });
    fireEvent.change(screen.getByLabelText(/service tag/i), { target: { value: 'tax' } });
    fireEvent.click(screen.getByRole('button', { name: /next: build/i }));
    fireEvent.click(screen.getByRole('button', { name: /add question/i }));
    fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'EIN' } });
    fireEvent.click(screen.getByRole('button', { name: /next: review/i }));
    fireEvent.click(screen.getByRole('button', { name: /create template/i }));

    await waitFor(() => expect(apiMock.createOnboardingTemplate).toHaveBeenCalledTimes(1));
    expect(apiMock.createOnboardingTemplate.mock.calls[0]![0]).toMatchObject({
      service_tag: 'tax',
    });
  });

  it("can't finish empty — Next: review is disabled with zero fields", async () => {
    renderWizard();
    chooseKind(/questionnaire/i);
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Empty' } });
    fireEvent.click(screen.getByRole('button', { name: /next: build/i }));
    // No fields added → can't advance to review.
    expect(screen.getByRole('button', { name: /next: review/i })).toBeDisabled();
  });
});

describe('OnboardingTemplateWizard — e-sign 3-call commit', () => {
  it('creates → uploads (pdf_version 1) → PATCHes fields + requires_esign', async () => {
    apiMock.createOnboardingTemplate.mockResolvedValue({ id: 42, name: 'Agreement' });
    apiMock.uploadOnboardingTemplatePdf.mockResolvedValue({ id: 42, pdf_version: 1 });
    apiMock.updateOnboardingTemplate.mockResolvedValue({ id: 42, name: 'Agreement' });
    renderWizard();

    chooseKind(/e-sign pdf/i);
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Agreement' } });
    fireEvent.click(screen.getByRole('button', { name: /next: build/i }));

    // Pick a PDF → pre-check (mocked) passes → the editor stub mounts.
    const file = new File([new Uint8Array([1, 2, 3])], 'doc.pdf', {
      type: 'application/pdf',
    });
    // jsdom's File lacks arrayBuffer() (real browsers have it) — the pre-check
    // calls it before pdf.js, so shim it here.
    Object.defineProperty(file, 'arrayBuffer', {
      value: () => Promise.resolve(new Uint8Array([1, 2, 3]).buffer),
    });
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });
    await screen.findByTestId('esign-editor-stub');

    // Before placing a signature field, review is blocked.
    expect(screen.getByRole('button', { name: /next: review/i })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: /stub place signature/i }));
    await waitFor(() =>
      expect(screen.getByTestId('esign-field-count')).toHaveTextContent('1'),
    );

    fireEvent.click(screen.getByRole('button', { name: /next: review/i }));
    fireEvent.click(screen.getByRole('button', { name: /create template/i }));

    await waitFor(() => expect(apiMock.updateOnboardingTemplate).toHaveBeenCalledTimes(1));

    // 1) create — no fields, no requires_esign for esign_pdf.
    const createPayload = apiMock.createOnboardingTemplate.mock.calls[0]![0];
    expect(createPayload).toMatchObject({ name: 'Agreement', kind: 'esign_pdf' });
    expect(createPayload).not.toHaveProperty('field_definitions');
    expect(createPayload).not.toHaveProperty('requires_esign');
    // 2) upload the picked file against the new id.
    expect(apiMock.uploadOnboardingTemplatePdf).toHaveBeenCalledWith(42, file);
    // 3) combined PATCH — fields (≥1 signature) + requires_esign, pdf_version 1.
    const [patchId, patchBody] = apiMock.updateOnboardingTemplate.mock.calls[0]!;
    expect(patchId).toBe(42);
    expect(patchBody).toMatchObject({ pdf_version: 1, requires_esign: true });
    expect(patchBody.field_definitions).toHaveLength(1);
    expect(patchBody.field_definitions[0]).toMatchObject({ kind: 'signature' });
  });
});

describe('OnboardingTemplateWizard — duplicate-name 422', () => {
  it('surfaces the error on the Name field and offers to restore a retired shell', async () => {
    apiMock.createOnboardingTemplate.mockRejectedValue({
      status_code: 422,
      detail: 'A template with this name already exists.',
    });
    apiMock.listOnboardingTemplates.mockResolvedValue([
      {
        id: 5,
        name: 'Intake',
        is_active: false,
        kind: 'questionnaire',
        has_pdf: false,
        pdf_version: 1,
        field_definitions: [],
        requires_esign: false,
        created_at: '2026-05-01T00:00:00Z',
        updated_at: '2026-05-01T00:00:00Z',
      },
    ]);
    apiMock.restoreOnboardingTemplate.mockResolvedValue({ id: 5, name: 'Intake' });
    renderWizard();

    chooseKind(/questionnaire/i);
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Intake' } });
    fireEvent.click(screen.getByRole('button', { name: /next: build/i }));
    fireEvent.click(screen.getByRole('button', { name: /add question/i }));
    fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'EIN' } });
    fireEvent.click(screen.getByRole('button', { name: /next: review/i }));
    fireEvent.click(screen.getByRole('button', { name: /create template/i }));

    // The 422 sends the user back to Basics with the error on the Name field and
    // a Restore offer for the retired same-name shell.
    expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
    const restore = await screen.findByRole('button', { name: /restore/i });
    fireEvent.click(restore);
    await waitFor(() =>
      expect(apiMock.restoreOnboardingTemplate).toHaveBeenCalledWith(5),
    );
  });
});

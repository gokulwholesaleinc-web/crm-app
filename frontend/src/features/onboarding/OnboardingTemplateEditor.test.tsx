/**
 * Behavioural tests for the onboarding field editor.
 *
 * The network boundary here is pdf.js (the PDF render pipeline), which jsdom
 * can't run — so we mock ONLY ``pdfjs-dist`` to resolve a fake one-page
 * document and a no-op render. Everything else (selection state, the stable
 * ``_key`` fix for finding #5, ``canSave`` gating, ``onSave`` payload
 * stripping) is the component's own logic and is exercised for real.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// --- Mock the PDF render pipeline (the only external boundary) ----------
const renderMock = vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() }));
const fakePage = {
  getViewport: () => ({ width: 612, height: 792 }),
  render: renderMock,
};
const fakeDoc = {
  numPages: 1,
  getPage: vi.fn(async () => fakePage),
  destroy: vi.fn(),
};

vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: {},
  getDocument: vi.fn(() => ({
    promise: Promise.resolve(fakeDoc),
    destroy: vi.fn(),
  })),
}));
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: 'worker.js' }));

import { OnboardingTemplateEditor } from './OnboardingTemplateEditor';
import type { OnboardingFieldDefinition } from '../../types';

// jsdom lacks canvas 2d + pointer capture; stub the bits the editor touches.
beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = (() => ({})) as never;
  HTMLElement.prototype.setPointerCapture = (() => {}) as never;
  HTMLElement.prototype.releasePointerCapture = (() => {}) as never;
});

function makeField(over: Partial<OnboardingFieldDefinition> = {}): OnboardingFieldDefinition {
  return {
    id: 'ein_number',
    kind: 'text',
    label: 'Federal EIN',
    description: '',
    required: false,
    prefill: null,
    page: 1,
    x: 100,
    y: 100,
    w: 120,
    h: 30,
    ...over,
  };
}

async function renderEditorWithField(
  field: OnboardingFieldDefinition,
  onSave = vi.fn().mockResolvedValue(undefined),
) {
  const utils = render(
    <OnboardingTemplateEditor
      isOpen
      onClose={vi.fn()}
      templateName="Intake packet"
      pdfUrl="blob:test"
      currentFields={[field]}
      onSave={onSave}
    />,
  );
  // Wait for the (mocked) PDF to load + render so the overlay boxes appear.
  await waitFor(() => expect(renderMock).toHaveBeenCalled());
  // The placed field renders a "Select …" button on the canvas overlay. The
  // overlay buttons call ``preventDefault`` on pointerdown (so a click doesn't
  // start a new drag); ``fireEvent.click`` exercises the React ``onClick``
  // directly without userEvent's full pointer sequence, which that
  // preventDefault would otherwise swallow.
  const selectBtn = await screen.findByRole('button', { name: /^Select / });
  fireEvent.click(selectBtn);
  // Wait for the per-field panel to mount (selection took effect).
  await screen.findByLabelText('Field id');
  return { ...utils, onSave };
}

describe('OnboardingTemplateEditor — finding #5 (id edit keeps selection)', () => {
  it('keeps the field selected and editable after its id is changed', async () => {
    await renderEditorWithField(makeField({ id: 'ein_number', label: 'Federal EIN' }));

    // Panel is open for the selected field.
    const idInput = screen.getByLabelText('Field id') as HTMLInputElement;
    expect(idInput.value).toBe('ein_number');
    expect(screen.getByLabelText('Label')).toHaveValue('Federal EIN');

    // Edit the (mutable) id — this used to orphan the selection.
    fireEvent.change(idInput, { target: { value: 'ein_number_2' } });

    // The panel must STILL be open, showing the new id and the same label.
    const idAfter = screen.getByLabelText('Field id') as HTMLInputElement;
    expect(idAfter.value).toBe('ein_number_2');
    expect(screen.getByLabelText('Label')).toHaveValue('Federal EIN');

    // And the label is still editable on the same (re-keyed) field.
    fireEvent.change(screen.getByLabelText('Label'), { target: { value: 'EIN #' } });
    expect(screen.getByLabelText('Label')).toHaveValue('EIN #');
  });
});

describe('OnboardingTemplateEditor — canSave gating + onSave payload', () => {
  it('blocks save while a field has a blank label, then strips _key on save', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    // Field with an empty label is invalid → Save disabled.
    await renderEditorWithField(makeField({ label: '' }), onSave);

    const saveBtn = screen.getByRole('button', { name: 'Save fields' });
    expect(saveBtn).toBeDisabled();
    expect(
      screen.getByText(/need a label and a valid, unique id before saving/i),
    ).toBeInTheDocument();

    // Fill the label → now valid → Save enabled.
    fireEvent.change(screen.getByLabelText('Label'), { target: { value: 'Federal EIN' } });
    await waitFor(() => expect(saveBtn).toBeEnabled());

    await userEvent.click(saveBtn);
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));

    // The persisted payload must NOT carry the internal _key.
    const savedFields = onSave.mock.calls[0][0] as Array<Record<string, unknown>>;
    expect(savedFields).toHaveLength(1);
    const saved = savedFields[0]!;
    expect(saved).not.toHaveProperty('_key');
    expect(saved.id).toBe('ein_number');
    expect(saved.label).toBe('Federal EIN');
  });
});

describe('OnboardingTemplateEditor — 409 stale-save handling', () => {
  it('surfaces the rejection message and does not re-clear the panel on a failed save', async () => {
    // onSave rejects like the parent would on a non-409 error path: editor
    // shows saveError and stays open. (The 409 close/refetch is owned by the
    // library page and covered in OnboardingLibraryPage.test.tsx.)
    const onSave = vi
      .fn()
      .mockRejectedValue({
        detail: "This template's PDF was replaced; reload before saving fields.",
        status_code: 409,
      });
    await renderEditorWithField(makeField({ label: 'Federal EIN' }), onSave);

    await userEvent.click(screen.getByRole('button', { name: 'Save fields' }));

    await waitFor(() =>
      expect(
        screen.getByText("This template's PDF was replaced; reload before saving fields."),
      ).toBeInTheDocument(),
    );
    // Editor stays open so the message is visible.
    expect(screen.getByText(/Define fields/)).toBeInTheDocument();
  });
});

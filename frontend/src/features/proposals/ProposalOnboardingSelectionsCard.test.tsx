/**
 * Regression test for the proposal onboarding-selection card's "Add a document"
 * picker (hotfix §0.1).
 *
 * The card used to filter the available templates on ``t.is_active && t.has_pdf``
 * for ALL kinds, which hid every questionnaire / upload_request template (they
 * carry no PDF by design) from proposal auto-send — even though the backend's
 * ``_assert_templates_active`` only requires a PDF for esign_pdf. The fix mirrors
 * the backend ``template_send_status`` gate: esign_pdf needs a PDF, a form kind
 * needs at least one authored field (the D2 empty-form guard) — so an empty form
 * is "needs setup", not offered. This pins that behaviour and keeps the picker in
 * lock-step with OnboardingSendPanel.
 *
 * The network boundary is the ``api/onboarding`` wrappers; they're mocked so the
 * card's real query/filter logic runs against controlled template fixtures.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  renderWithProviders,
  screen,
  waitFor,
} from '../../test-utils/renderWithProviders';
import type { OnboardingTemplate } from '../../types';

const onboardingApiMock = vi.hoisted(() => ({
  listOnboardingTemplates: vi.fn(),
  listProposalOnboardingSelections: vi.fn(),
  setProposalOnboardingSelections: vi.fn(),
  reorderProposalOnboardingSelections: vi.fn(),
  removeProposalOnboardingSelection: vi.fn(),
}));
vi.mock('../../api/onboarding', () => onboardingApiMock);

vi.mock('../../utils/toast', () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

import { ProposalOnboardingSelectionsCard } from './ProposalOnboardingSelectionsCard';

function makeTemplate(over: Partial<OnboardingTemplate> = {}): OnboardingTemplate {
  return {
    id: 1,
    name: 'Template',
    description: null,
    service_tag: null,
    owner_id: null,
    kind: 'esign_pdf',
    has_pdf: true,
    pdf_version: 1,
    field_definitions: [],
    requires_esign: false,
    is_active: true,
    created_at: '2026-06-01T00:00:00Z',
    updated_at: '2026-06-01T00:00:00Z',
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  onboardingApiMock.listProposalOnboardingSelections.mockResolvedValue([]);
});

describe('ProposalOnboardingSelectionsCard "Add a document" picker', () => {
  it('offers active questionnaire/upload templates without a PDF, and esign only when it has a PDF', async () => {
    const questionnaire = makeTemplate({
      id: 10,
      name: 'Intake Questionnaire',
      kind: 'questionnaire',
      has_pdf: false,
      field_definitions: [{ id: 'q1', kind: 'short_text', label: 'Your name', required: true }],
    });
    const upload = makeTemplate({
      id: 11,
      name: 'Document Upload',
      kind: 'upload_request',
      has_pdf: false,
      field_definitions: [{ id: 'f1', kind: 'file_upload', label: 'Upload your ID', required: true }],
    });
    // An empty form (no fields) must NOT be offered — the backend's D2 guard
    // 422s it, so the picker hides it just like a PDF-less esign template.
    const emptyForm = makeTemplate({
      id: 15,
      name: 'Empty Questionnaire',
      kind: 'questionnaire',
      has_pdf: false,
      field_definitions: [],
    });
    const esignReady = makeTemplate({
      id: 12,
      name: 'Signed Agreement',
      kind: 'esign_pdf',
      has_pdf: true,
    });
    const esignNoPdf = makeTemplate({
      id: 13,
      name: 'Draft Agreement',
      kind: 'esign_pdf',
      has_pdf: false,
    });
    const retired = makeTemplate({
      id: 14,
      name: 'Retired Questionnaire',
      kind: 'questionnaire',
      has_pdf: false,
      is_active: false,
    });
    onboardingApiMock.listOnboardingTemplates.mockResolvedValue([
      questionnaire,
      upload,
      esignReady,
      esignNoPdf,
      retired,
      emptyForm,
    ]);

    renderWithProviders(
      <ProposalOnboardingSelectionsCard proposalId={1} isLocked={false} />,
    );

    // The questionnaire / upload / PDF-backed esign templates are offered…
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Add Intake Questionnaire to onboarding' }),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByRole('button', { name: 'Add Document Upload to onboarding' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Add Signed Agreement to onboarding' }),
    ).toBeInTheDocument();

    // …but the PDF-less esign, the retired, and the empty (field-less) form are not.
    expect(
      screen.queryByRole('button', { name: 'Add Draft Agreement to onboarding' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'Add Retired Questionnaire to onboarding',
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'Add Empty Questionnaire to onboarding',
      }),
    ).not.toBeInTheDocument();
  });

  it('shows the neutral empty state when no template is selectable', async () => {
    onboardingApiMock.listOnboardingTemplates.mockResolvedValue([
      makeTemplate({ id: 20, kind: 'esign_pdf', has_pdf: false }),
    ]);

    renderWithProviders(
      <ProposalOnboardingSelectionsCard proposalId={1} isLocked={false} />,
    );

    await waitFor(() => {
      expect(
        screen.getByText(/No active templates are available\./i),
      ).toBeInTheDocument();
    });
  });
});

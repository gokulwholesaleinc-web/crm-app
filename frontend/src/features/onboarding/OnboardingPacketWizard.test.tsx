/**
 * Behavioural tests for the "Build a packet" wizard.
 *
 * The ``api/onboarding`` wrappers are mocked; the wizard's real step logic,
 * draft-list ordering, and payload assembly run. Pins: e-sign templates are
 * excluded from the clone picker (audit P0#4); the create payload carries the
 * documents in the order they were added, each with its source + name.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  renderWithProviders,
  screen,
  waitFor,
  fireEvent,
} from '../../test-utils/renderWithProviders';
import type { OnboardingStarter, OnboardingTemplate } from '../../types';

const apiMock = vi.hoisted(() => ({
  listOnboardingStarters: vi.fn(),
  listOnboardingTemplates: vi.fn(),
  createOnboardingBundle: vi.fn(),
}));
vi.mock('../../api/onboarding', () => apiMock);

vi.mock('../../utils/toast', () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

import { OnboardingPacketWizard } from './OnboardingPacketWizard';

function tmpl(over: Partial<OnboardingTemplate> = {}): OnboardingTemplate {
  return {
    id: 1,
    name: 'Template',
    description: null,
    service_tag: null,
    owner_id: null,
    kind: 'questionnaire',
    has_pdf: false,
    pdf_version: 1,
    field_definitions: [],
    requires_esign: false,
    is_active: true,
    created_at: '2026-06-01T00:00:00Z',
    updated_at: '2026-06-01T00:00:00Z',
    ...over,
  };
}

const STARTERS: OnboardingStarter[] = [
  { key: 'admin-information', name: 'Admin Info', description: null, kind: 'questionnaire', service_tag: null },
];

beforeEach(() => {
  vi.clearAllMocks();
  apiMock.listOnboardingStarters.mockResolvedValue(STARTERS);
  apiMock.createOnboardingBundle.mockResolvedValue({
    id: 99,
    name: 'My Packet',
    description: null,
    is_active: true,
    item_count: 2,
    send_ready: true,
    created_at: '2026-06-05T00:00:00Z',
    updated_at: '2026-06-05T00:00:00Z',
    members: [],
  });
});

describe('OnboardingPacketWizard', () => {
  it('excludes e-sign templates from the clone picker and submits items in order', async () => {
    apiMock.listOnboardingTemplates.mockResolvedValue([
      tmpl({ id: 10, name: 'Brand Questionnaire', kind: 'questionnaire' }),
      tmpl({ id: 11, name: 'Signed Contract', kind: 'esign_pdf', has_pdf: true }),
    ]);

    renderWithProviders(<OnboardingPacketWizard isOpen onClose={() => {}} />);

    // Step 1 — basics.
    fireEvent.change(screen.getByLabelText('Packet name'), {
      target: { value: 'My Packet' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Next: documents' }));

    // Step 2 — the starter + the questionnaire are offered; the e-sign isn't.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Add starter Admin Info' })).toBeInTheDocument(),
    );
    expect(
      screen.getByRole('button', { name: 'Copy template Brand Questionnaire' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Copy template Signed Contract' }),
    ).not.toBeInTheDocument();

    // Add the starter first, then the cloned questionnaire (order matters).
    fireEvent.click(screen.getByRole('button', { name: 'Add starter Admin Info' }));
    fireEvent.click(screen.getByRole('button', { name: 'Copy template Brand Questionnaire' }));

    fireEvent.click(screen.getByRole('button', { name: 'Next: review' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create packet' }));

    await waitFor(() => expect(apiMock.createOnboardingBundle).toHaveBeenCalledTimes(1));
    const payload = apiMock.createOnboardingBundle.mock.calls[0][0];
    expect(payload.name).toBe('My Packet');
    expect(payload.items).toEqual([
      { source: 'starter', starter_key: 'admin-information', name: 'Admin Info' },
      { source: 'clone', source_template_id: 10, name: 'Brand Questionnaire (copy)' },
    ]);
  });

  it('blocks advancing past documents until at least one is added', async () => {
    apiMock.listOnboardingTemplates.mockResolvedValue([]);
    renderWithProviders(<OnboardingPacketWizard isOpen onClose={() => {}} />);

    fireEvent.change(screen.getByLabelText('Packet name'), {
      target: { value: 'Empty Packet' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Next: documents' }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Next: review' })).toBeDisabled(),
    );
  });
});

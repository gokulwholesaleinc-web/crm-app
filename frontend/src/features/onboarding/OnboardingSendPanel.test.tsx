/**
 * Behavioural tests for the onboarding send panel's saved-packet preselect +
 * readiness gate (audit B5 / §4.7 / §5).
 *
 * The ``api/onboarding`` + ``api/contacts`` wrappers are mocked. A contact is
 * pre-picked via ``?contact=`` so the document UI renders without driving the
 * SearchableSelect. Pins: picking a saved packet preselects its members in the
 * SAVED order and sends them in that order; a packet with a not-ready member
 * surfaces a "needs setup" block and disables sending (the flag is READ from
 * the API, never re-derived).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  renderWithProviders,
  screen,
  waitFor,
  fireEvent,
} from '../../test-utils/renderWithProviders';
import type {
  OnboardingBundleDetail,
  OnboardingBundleSummary,
  OnboardingTemplate,
} from '../../types';

const apiMock = vi.hoisted(() => ({
  createOnboardingPacket: vi.fn(),
  listOnboardingBundles: vi.fn(),
  getOnboardingBundle: vi.fn(),
}));
vi.mock('../../api/onboarding', () => apiMock);

const contactsMock = vi.hoisted(() => ({ listContacts: vi.fn() }));
vi.mock('../../api/contacts', () => contactsMock);

vi.mock('../../utils/toast', () => ({ showSuccess: vi.fn(), showError: vi.fn() }));

// The packet list pulls its own queries; stub it out — irrelevant here.
vi.mock('./OnboardingPacketList', () => ({
  OnboardingPacketList: () => null,
  PACKETS_KEY: ['onboarding-packets'],
}));

import { OnboardingSendPanel } from './OnboardingSendPanel';

function tmpl(over: Partial<OnboardingTemplate> = {}): OnboardingTemplate {
  return {
    id: 1, name: 'Template', description: null, service_tag: null, owner_id: null,
    kind: 'questionnaire', has_pdf: false, pdf_version: 1, field_definitions: [],
    requires_esign: false, is_active: true,
    created_at: '2026-06-01T00:00:00Z', updated_at: '2026-06-01T00:00:00Z',
    ...over,
  };
}

const Q = tmpl({ id: 10, name: 'Intake', kind: 'questionnaire', has_pdf: false });
const ESIGN_READY = tmpl({ id: 11, name: 'Agreement', kind: 'esign_pdf', has_pdf: true });
const ESIGN_BLANK = tmpl({ id: 12, name: 'Blank Agreement', kind: 'esign_pdf', has_pdf: false });

const READY_BUNDLE: OnboardingBundleSummary = {
  id: 7, name: 'Full Onboarding', description: null, is_active: true,
  item_count: 2, send_ready: true,
  created_at: '2026-06-05T00:00:00Z', updated_at: '2026-06-05T00:00:00Z',
};
const NEEDS_SETUP_BUNDLE: OnboardingBundleSummary = { ...READY_BUNDLE, id: 8, name: 'Half-built', send_ready: false };

beforeEach(() => {
  vi.clearAllMocks();
  contactsMock.listContacts.mockResolvedValue({
    items: [{ id: 5, full_name: 'Acme Client', email: 'client@acme.test' }],
    total: 1,
  });
  apiMock.createOnboardingPacket.mockResolvedValue({ id: 1, access_url: 'https://x/y' });
});

function renderPanel(templates: OnboardingTemplate[]) {
  return renderWithProviders(<OnboardingSendPanel templates={templates} />, {
    initialRoute: '/?contact=5',
  });
}

describe('OnboardingSendPanel saved-packet preselect', () => {
  it('preselects a ready packet in saved order and sends template_ids in that order', async () => {
    apiMock.listOnboardingBundles.mockResolvedValue([READY_BUNDLE]);
    const detail: OnboardingBundleDetail = {
      ...READY_BUNDLE,
      members: [
        { item_id: 1, template_id: 11, display_order: 0, name: 'Agreement', kind: 'esign_pdf', requires_esign: true, is_active: true, has_pdf: true, send_ready: true, send_reason: null },
        { item_id: 2, template_id: 10, display_order: 1, name: 'Intake', kind: 'questionnaire', requires_esign: false, is_active: true, has_pdf: false, send_ready: true, send_reason: null },
      ],
    };
    apiMock.getOnboardingBundle.mockResolvedValue(detail);

    renderPanel([ESIGN_READY, Q]);

    fireEvent.change(await screen.findByLabelText('Recipient email'), {
      target: { value: 'client@acme.test' },
    });
    fireEvent.change(
      await screen.findByLabelText('Start from a saved packet (optional)'),
      { target: { value: '7' } },
    );

    // Send button enables once the ready packet is preselected.
    const sendBtn = await screen.findByRole('button', { name: 'Send onboarding email' });
    await waitFor(() => expect(sendBtn).not.toBeDisabled());
    fireEvent.click(sendBtn);

    await waitFor(() => expect(apiMock.createOnboardingPacket).toHaveBeenCalledTimes(1));
    const payload = apiMock.createOnboardingPacket.mock.calls[0][0];
    // Saved order preserved: template 11 (order 0) before 10 (order 1).
    expect(payload.template_ids).toEqual([11, 10]);
  });

  it('blocks sending a packet with a not-ready member and names it', async () => {
    apiMock.listOnboardingBundles.mockResolvedValue([NEEDS_SETUP_BUNDLE]);
    const detail: OnboardingBundleDetail = {
      ...NEEDS_SETUP_BUNDLE,
      members: [
        { item_id: 1, template_id: 10, display_order: 0, name: 'Intake', kind: 'questionnaire', requires_esign: false, is_active: true, has_pdf: false, send_ready: true, send_reason: null },
        { item_id: 2, template_id: 12, display_order: 1, name: 'Blank Agreement', kind: 'esign_pdf', requires_esign: false, is_active: true, has_pdf: false, send_ready: false, send_reason: 'This e-sign template has no PDF uploaded yet.' },
      ],
    };
    apiMock.getOnboardingBundle.mockResolvedValue(detail);

    renderPanel([Q, ESIGN_BLANK]);

    fireEvent.change(await screen.findByLabelText('Recipient email'), {
      target: { value: 'client@acme.test' },
    });
    fireEvent.change(
      await screen.findByLabelText('Start from a saved packet (optional)'),
      { target: { value: '8' } },
    );

    // The not-ready document is named in a "needs setup" alert…
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/needs?\s+setup/i),
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Blank Agreement');
    // …and sending is blocked.
    expect(screen.getByRole('button', { name: 'Send onboarding email' })).toBeDisabled();
    expect(apiMock.createOnboardingPacket).not.toHaveBeenCalled();
  });
});

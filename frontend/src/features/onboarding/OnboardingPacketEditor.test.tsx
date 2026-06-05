/**
 * Behavioural tests for the saved-packet composition editor (rename / reorder /
 * add / remove). The api/onboarding wrappers are mocked; the editor's real
 * mutation wiring runs.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  renderWithProviders,
  screen,
  waitFor,
  fireEvent,
} from '../../test-utils/renderWithProviders';
import { useAuthStore } from '../../store/authStore';
import type { OnboardingBundleDetail, OnboardingTemplate } from '../../types';

const apiMock = vi.hoisted(() => ({
  getOnboardingBundle: vi.fn(),
  listOnboardingTemplates: vi.fn(),
  updateOnboardingBundle: vi.fn(),
  reorderOnboardingBundle: vi.fn(),
  addOnboardingBundleItem: vi.fn(),
  removeOnboardingBundleItem: vi.fn(),
}));
vi.mock('../../api/onboarding', () => apiMock);
vi.mock('../../utils/toast', () => ({ showSuccess: vi.fn(), showError: vi.fn() }));

import { OnboardingPacketEditor } from './OnboardingPacketEditor';

function member(over: Partial<OnboardingBundleDetail['members'][number]>) {
  return {
    item_id: 1, template_id: 1, display_order: 0, name: 'Doc', kind: 'questionnaire' as const,
    requires_esign: false, is_active: true, has_pdf: false, send_ready: true, send_reason: null,
    ...over,
  };
}

const DETAIL: OnboardingBundleDetail = {
  id: 7, name: 'My Packet', description: null, is_active: true, item_count: 2,
  send_ready: true, created_at: '2026-06-05T00:00:00Z', updated_at: '2026-06-05T00:00:00Z',
  members: [
    member({ item_id: 100, template_id: 10, display_order: 0, name: 'First' }),
    member({ item_id: 101, template_id: 11, display_order: 1, name: 'Second' }),
  ],
};

function addable(): OnboardingTemplate {
  return {
    id: 20, name: 'Extra Template', description: null, service_tag: null, owner_id: null,
    kind: 'questionnaire', has_pdf: false, pdf_version: 1, field_definitions: [],
    requires_esign: false, is_active: true,
    created_at: '2026-06-01T00:00:00Z', updated_at: '2026-06-01T00:00:00Z',
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthStore.setState({ isAuthenticated: true, isLoading: false, token: 'test-token' });
  apiMock.getOnboardingBundle.mockResolvedValue(DETAIL);
  apiMock.listOnboardingTemplates.mockResolvedValue([addable()]);
  apiMock.reorderOnboardingBundle.mockResolvedValue(DETAIL);
  apiMock.addOnboardingBundleItem.mockResolvedValue(DETAIL);
  apiMock.removeOnboardingBundleItem.mockResolvedValue(undefined);
  apiMock.updateOnboardingBundle.mockResolvedValue(DETAIL);
});

describe('OnboardingPacketEditor', () => {
  it('reorders by swapping item ids when moving a member down', async () => {
    renderWithProviders(<OnboardingPacketEditor bundleId={7} onClose={() => {}} />);
    await screen.findByText('First');

    fireEvent.click(screen.getByRole('button', { name: 'Move First down' }));
    await waitFor(() => expect(apiMock.reorderOnboardingBundle).toHaveBeenCalledTimes(1));
    expect(apiMock.reorderOnboardingBundle.mock.calls[0]).toEqual([7, [101, 100]]);
  });

  it('adds an existing template and removes a member', async () => {
    renderWithProviders(<OnboardingPacketEditor bundleId={7} onClose={() => {}} />);
    await screen.findByText('First');
    // The add-picker is fed by a SEPARATE templates query; wait for its option
    // to land (and the select to enable) before selecting, else the change is
    // swallowed by the still-disabled "No templates to add" select.
    await screen.findByRole('option', { name: 'Extra Template' });

    fireEvent.change(screen.getByLabelText('Add an existing template'), {
      target: { value: '20' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(apiMock.addOnboardingBundleItem).toHaveBeenCalledWith(7, 20));

    fireEvent.click(screen.getByRole('button', { name: 'Remove First' }));
    await waitFor(() => expect(apiMock.removeOnboardingBundleItem).toHaveBeenCalledWith(7, 100));
  });

  it('renames the packet', async () => {
    renderWithProviders(<OnboardingPacketEditor bundleId={7} onClose={() => {}} />);
    await screen.findByText('First');

    fireEvent.change(screen.getByLabelText('Packet name'), {
      target: { value: 'Renamed Packet' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save name' }));
    await waitFor(() =>
      expect(apiMock.updateOnboardingBundle).toHaveBeenCalledWith(7, { name: 'Renamed Packet' }),
    );
  });
});

/**
 * Behavioural tests for the shared packet list + the D5 uploads surface.
 *
 * The api/onboarding + api/attachments wrappers are the network boundary and
 * are mocked; the component's own logic (rendering, the lazy files fetch on
 * expand, the download handler) runs for real.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, waitFor } from '../../test-utils/renderWithProviders';
import userEvent from '@testing-library/user-event';

import { OnboardingPacketList } from './OnboardingPacketList';
import type { OnboardingPacket, OnboardingPacketDetail } from '../../types';

const listOnboardingPackets = vi.fn();
const getOnboardingPacket = vi.fn();
const downloadAttachmentFile = vi.fn();
const showError = vi.fn();

vi.mock('../../api/onboarding', () => ({
  listOnboardingPackets: (...a: unknown[]) => listOnboardingPackets(...a),
  getOnboardingPacket: (...a: unknown[]) => getOnboardingPacket(...a),
  revokeOnboardingPacket: vi.fn(),
  retryOnboardingPacket: vi.fn(),
  resendOnboardingCompletionNotice: vi.fn(),
  resendOnboardingPacketInvite: vi.fn(),
  regenerateOnboardingPacketLink: vi.fn(),
}));

vi.mock('../../api/attachments', () => ({
  downloadAttachmentFile: (...a: unknown[]) => downloadAttachmentFile(...a),
}));

vi.mock('../../utils/toast', () => ({
  showSuccess: vi.fn(),
  showError: (...a: unknown[]) => showError(...a),
}));

const PACKET: OnboardingPacket = {
  id: 7,
  contact_id: 5,
  status: 'completed',
  recipient_email_masked: 'c***@example.com',
  recipient_name: 'Client',
  document_count: 1,
  created_at: '2026-06-04T00:00:00Z',
  token_expires_at: '2026-07-04T00:00:00Z',
  emails: [],
};

const DETAIL: OnboardingPacketDetail = {
  ...PACKET,
  documents: [],
  uploads: [
    {
      id: 3,
      packet_document_id: 9,
      field_id: 'u_logo',
      attachment_id: 42,
      original_filename: 'logo.png',
      byte_size: 2048,
      mime_type: 'image/png',
      sensitive: true,
    },
  ],
};

describe('OnboardingPacketList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listOnboardingPackets.mockResolvedValue([PACKET]);
    getOnboardingPacket.mockResolvedValue(DETAIL);
  });

  it('renders the packet status and document count', async () => {
    renderWithProviders(<OnboardingPacketList contactId={5} />);
    expect(await screen.findByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('1 document')).toBeInTheDocument();
  });

  it('reveals the client-uploaded files on expanding "Files"', async () => {
    const user = userEvent.setup();
    renderWithProviders(<OnboardingPacketList contactId={5} />);
    await screen.findByText('Completed');

    await user.click(screen.getByRole('button', { name: 'Files' }));

    expect(await screen.findByText('logo.png')).toBeInTheDocument();
    expect(screen.getByText('Sensitive')).toBeInTheDocument();
    expect(getOnboardingPacket).toHaveBeenCalledWith(7);
  });

  it('downloads an uploaded file by its attachment id', async () => {
    const user = userEvent.setup();
    downloadAttachmentFile.mockResolvedValue(undefined);
    renderWithProviders(<OnboardingPacketList contactId={5} />);
    await screen.findByText('Completed');

    await user.click(screen.getByRole('button', { name: 'Files' }));
    await screen.findByText('logo.png');
    await user.click(screen.getByRole('button', { name: 'Download logo.png' }));

    await waitFor(() =>
      expect(downloadAttachmentFile).toHaveBeenCalledWith(42, 'logo.png'),
    );
  });

  it('shows an error when the files fetch fails', async () => {
    const user = userEvent.setup();
    getOnboardingPacket.mockRejectedValue(new Error('boom'));
    renderWithProviders(<OnboardingPacketList contactId={5} />);
    await screen.findByText('Completed');

    await user.click(screen.getByRole('button', { name: 'Files' }));
    expect(await screen.findByText('Failed to load files.')).toBeInTheDocument();
  });

  it('disables download for an orphaned (null attachment_id) upload', async () => {
    const user = userEvent.setup();
    getOnboardingPacket.mockResolvedValue({
      ...DETAIL,
      uploads: [{ ...DETAIL.uploads![0], attachment_id: null }],
    });
    renderWithProviders(<OnboardingPacketList contactId={5} />);
    await screen.findByText('Completed');

    await user.click(screen.getByRole('button', { name: 'Files' }));
    const btn = await screen.findByRole('button', { name: 'Download logo.png' });
    expect(btn).toBeDisabled();
    await user.click(btn);
    expect(downloadAttachmentFile).not.toHaveBeenCalled();
  });

  it('toasts when a download fails', async () => {
    const user = userEvent.setup();
    downloadAttachmentFile.mockRejectedValue(new Error('nope'));
    renderWithProviders(<OnboardingPacketList contactId={5} />);
    await screen.findByText('Completed');

    await user.click(screen.getByRole('button', { name: 'Files' }));
    await screen.findByText('logo.png');
    await user.click(screen.getByRole('button', { name: 'Download logo.png' }));

    await waitFor(() =>
      expect(showError).toHaveBeenCalledWith('Failed to download the file.'),
    );
  });
});

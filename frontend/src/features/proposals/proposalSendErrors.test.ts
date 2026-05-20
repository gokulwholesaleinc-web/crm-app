import { describe, expect, it } from 'vitest';
import {
  buildProposalSendFailure,
  isGmailReconnectSendError,
} from './proposalSendErrors';
import { GMAIL_SETTINGS_PATH } from '../../utils/integrationLinks';

describe('proposalSendErrors', () => {
  it('classifies Gmail reconnect failures and returns a settings action', () => {
    const failure = buildProposalSendFailure(
      'Your Gmail account is not connected. Connect it under Settings -> Integrations before sending.',
    );

    expect(isGmailReconnectSendError(failure.message)).toBe(true);
    expect(failure.title).toBe('Reconnect Gmail to send this proposal');
    expect(failure.action).toEqual({
      label: 'Open Settings -> Gmail',
      to: GMAIL_SETTINGS_PATH,
    });
  });

  it('keeps non-Gmail backend details visible without a reconnect action', () => {
    const failure = buildProposalSendFailure(
      'Place signature and date areas on every signing document before sending (Agreement.pdf)',
    );

    expect(failure.title).toBe('Proposal was not sent');
    expect(failure.message).toContain('Place signature and date areas');
    expect(failure.action).toBeUndefined();
  });
});

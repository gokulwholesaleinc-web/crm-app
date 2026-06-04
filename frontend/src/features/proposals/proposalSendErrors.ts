import { GMAIL_SETTINGS_PATH } from '../../utils/integrationLinks';
import { isGmailReconnectSendError } from '../../utils/gmailSendError';

// Re-exported so existing import sites (and tests) keep resolving it here.
export { isGmailReconnectSendError };

export interface ProposalSendFailure {
  title: string;
  message: string;
  action?: {
    label: string;
    to: string;
  };
}

export function buildProposalSendFailure(detail: string | null): ProposalSendFailure {
  const message = detail || 'Failed to send proposal';

  if (isGmailReconnectSendError(message)) {
    return {
      title: 'Reconnect Gmail to send this proposal',
      message,
      action: {
        label: 'Open Settings -> Gmail',
        to: GMAIL_SETTINGS_PATH,
      },
    };
  }

  return {
    title: 'Proposal was not sent',
    message,
  };
}

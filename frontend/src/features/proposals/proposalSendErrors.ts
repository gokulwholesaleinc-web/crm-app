import { GMAIL_SETTINGS_PATH } from '../../utils/integrationLinks';

export interface ProposalSendFailure {
  title: string;
  message: string;
  action?: {
    label: string;
    to: string;
  };
}

const GMAIL_RECONNECT_PATTERNS = [
  /gmail account is not connected/i,
  /gmail connection has expired/i,
  /reconnect.*gmail/i,
  /connect.*gmail/i,
];

export function isGmailReconnectSendError(message: string | null | undefined): boolean {
  if (!message) return false;
  return GMAIL_RECONNECT_PATTERNS.some((pattern) => pattern.test(message));
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

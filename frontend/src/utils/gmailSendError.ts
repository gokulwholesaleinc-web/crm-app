/**
 * Shared detection for "your Gmail isn't connected / has expired" send errors.
 *
 * Proposal sends and onboarding sends both surface the same backend
 * `assert_gmail_connected` ValueError (mapped to a 400 with the message in
 * `detail`). The UI maps it to a Connect-Gmail prompt (Settings → Integrations)
 * instead of a generic failure toast. Kept here so both features share one
 * matcher rather than drifting copies.
 */
const GMAIL_RECONNECT_PATTERNS = [
  /gmail account is not connected/i,
  /gmail connection has expired/i,
  /reconnect.*gmail/i,
  /connect.*gmail/i,
];

export function isGmailReconnectSendError(
  message: string | null | undefined,
): boolean {
  if (!message) return false;
  return GMAIL_RECONNECT_PATTERNS.some((pattern) => pattern.test(message));
}

/**
 * Single source of truth for the company/legal specifics shown on the public
 * Privacy Policy and Terms of Service pages (and linked from the OAuth consent
 * screen at https://www.linkcreativeagency.com/privacy and /terms).
 *
 * TODO (confirm with Lorenzo / counsel before relying on these in production):
 *  - LEGAL_ENTITY: the exact registered entity name (e.g. "LinkCreative Agency LLC").
 *  - PRIVACY_EMAIL / LEGAL_EMAIL: the real contact inboxes.
 *  - GOVERNING_LAW / VENUE: the specific U.S. state for the Terms.
 *  - LAST_UPDATED: bump whenever the wording changes.
 */
export const COMPANY_NAME = 'LinkCreative';
export const LEGAL_ENTITY = 'LinkCreative'; // TODO: exact registered entity name
export const APP_URL = 'https://www.linkcreativeagency.com';
export const PRIVACY_EMAIL = 'privacy@linkcreativeagency.com'; // TODO: confirm
export const LEGAL_EMAIL = 'legal@linkcreativeagency.com'; // TODO: confirm
// TODO: set a specific U.S. state once confirmed (e.g. "the State of Texas").
export const GOVERNING_LAW =
  'the laws of the United States and the U.S. state in which ' +
  `${LEGAL_ENTITY} is established`;
export const LAST_UPDATED = 'June 1, 2026';

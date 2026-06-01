/**
 * Single source of truth for the company/legal specifics shown on the public
 * Privacy Policy and Terms of Service pages (and linked from the OAuth consent
 * screen at https://www.linkcreativeagency.com/privacy and /terms).
 *
 * Confirmed by the business 2026-06-01. One interim value remains:
 *  - PRIVACY_EMAIL / LEGAL_EMAIL: currently a working owner/forwarding inbox on
 *    a different domain ("for now"); swap to a dedicated Link Creative inbox
 *    (e.g. privacy@linkcreativeagency.com) once it exists and receives mail.
 *  - LAST_UPDATED: bump whenever the wording changes.
 */
export const COMPANY_NAME = 'Link Creative';
export const LEGAL_ENTITY = 'Link Creative Co';
export const COMPANY_ADDRESS = '350 W Ontario St #5E, Chicago, IL 60654';
export const APP_URL = 'https://www.linkcreativeagency.com';
export const PRIVACY_EMAIL = 'Harsh@midwestsystemsolutions.com'; // interim — see note above
export const LEGAL_EMAIL = 'Harsh@midwestsystemsolutions.com'; // interim — see note above
export const GOVERNING_LAW = 'the laws of the State of Illinois';
export const LAST_UPDATED = 'June 1, 2026';

/**
 * Client-side mirror of the backend onboarding-upload allow-list.
 *
 * Source of truth is the backend: ``ONBOARDING_UPLOAD_EXTENSIONS``
 * (attachments/service.py) + ``_MIME_BY_EXT`` (onboarding/uploads.py). This is a
 * convenience hint for the native file picker only — the server's extension
 * allow-list + magic-byte sniff remain the authoritative backstop, so a client
 * that ignores ``accept`` still can't land a disallowed file. Keep this in sync
 * if the backend set changes (§F decision #4: pdf/png/jpg/jpeg/webp/gif/docx).
 */
export const ONBOARDING_UPLOAD_EXTENSIONS = [
  'pdf',
  'png',
  'jpg',
  'jpeg',
  'webp',
  'gif',
  'docx',
] as const;

export const ONBOARDING_UPLOAD_MIME_TYPES = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
] as const;

/** The ``accept`` attribute value: dotted extensions + MIME types. */
export const ONBOARDING_UPLOAD_ACCEPT = [
  ...ONBOARDING_UPLOAD_EXTENSIONS.map((ext) => `.${ext}`),
  ...ONBOARDING_UPLOAD_MIME_TYPES,
].join(',');

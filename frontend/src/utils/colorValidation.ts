/**
 * Color validation helpers for untrusted tenant-supplied branding colors.
 *
 * Public quote/proposal views render server-provided `branding.primary_color`
 * etc. directly into inline `style={{}}` attributes. React escapes CSS
 * property values, but a malformed color string can still leak out of the
 * intended property and break layout or be used to inject unexpected styling.
 * These helpers collapse anything that isn't a strict hex color to a fallback.
 */

const HEX_COLOR_RE = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;

/**
 * Returns `input` if it's a well-formed `#rgb`, `#rrggbb`, or `#rrggbbaa`
 * hex string; otherwise returns `fallback`. Trims whitespace before checking
 * and treats `null`/`undefined` as invalid.
 */
export function sanitizeHexColor(
  input: string | null | undefined,
  fallback: string
): string {
  if (typeof input !== 'string') return fallback;
  const trimmed = input.trim();
  return HEX_COLOR_RE.test(trimmed) ? trimmed : fallback;
}

/** True if `input` is a valid hex color literal. */
export function isValidHexColor(input: string | null | undefined): boolean {
  return (
    typeof input === 'string' && HEX_COLOR_RE.test(input.trim())
  );
}

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

/**
 * Concatenate a 2-digit alpha suffix onto a hex color, normalizing the input
 * so the result is always a valid 8-digit `#rrggbbaa` literal.
 *
 * The naive pattern `${color}${alpha}` quietly produces invalid CSS for
 * `#rgb` (5 chars) and `#rrggbbaa` (10 chars) inputs — browsers drop the
 * rule and the styled element renders unbranded. Use this helper for every
 * tenant-color + alpha concatenation so 3- and 8-digit hexes Just Work.
 */
export function withAlpha(color: string, alphaHex: string): string {
  if (typeof color !== 'string') return 'transparent';
  const trimmed = color.trim();
  if (!HEX_COLOR_RE.test(trimmed)) return 'transparent';
  const body = trimmed.slice(1);
  const rrggbb = body.length === 3
    ? body.replace(/(.)/g, '$1$1')
    : body.slice(0, 6);
  return `#${rrggbb}${alphaHex}`;
}

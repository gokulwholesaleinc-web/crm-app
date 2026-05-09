export function normalizePhone(raw: string): string {
  const trimmed = raw.trim();
  const hasLeadingPlus = trimmed.startsWith('+');
  const digits = trimmed.replace(/[^\d]/g, '');
  return hasLeadingPlus ? `+${digits}` : digits;
}

export function normalizeEmail(raw: string): string {
  return raw.trim().toLowerCase();
}

export interface ClampNumberOptions {
  min?: number;
  max?: number;
  allowDecimal?: boolean;
}

export function clampNumberInput(raw: string, opts: ClampNumberOptions = {}): string {
  const { min, max, allowDecimal = true } = opts;
  const allowNegative = min !== undefined && min < 0;
  let allowed = '0123456789';
  if (allowDecimal) allowed += '.';
  if (allowNegative) allowed += '-';
  let cleaned = '';
  let seenDot = false;
  for (const ch of raw) {
    if (!allowed.includes(ch)) continue;
    if (ch === '.') {
      if (seenDot) continue;
      seenDot = true;
    }
    if (ch === '-' && cleaned.length > 0) continue;
    cleaned += ch;
  }
  if (cleaned === '' || cleaned === '-' || cleaned === '.') return '0';
  const num = parseFloat(cleaned);
  if (!Number.isFinite(num)) return '0';
  if (min !== undefined && num < min) return String(min);
  if (max !== undefined && num > max) return String(max);
  return cleaned;
}

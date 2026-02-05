/**
 * Centralized formatting utilities for consistent data display across the CRM application.
 */

/**
 * Format a number as currency
 *
 * @param amount - The numeric amount to format
 * @param currency - The currency code (default: 'USD')
 * @param options - Additional Intl.NumberFormat options
 * @returns Formatted currency string
 *
 * @example
 * formatCurrency(50000) // '$50,000'
 * formatCurrency(1234.56, 'EUR') // '1.235 EUR' (in EUR format)
 */
export function formatCurrency(
  amount: number | null | undefined,
  currency: string = 'USD',
  options?: {
    minimumFractionDigits?: number;
    maximumFractionDigits?: number;
    showCents?: boolean;
  }
): string {
  if (amount === null || amount === undefined) {
    return '-';
  }

  const { minimumFractionDigits = 0, maximumFractionDigits = 0 } = options ?? {};

  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(amount);
}

/**
 * Format a number as currency with cents
 *
 * @param amount - The numeric amount to format
 * @param currency - The currency code (default: 'USD')
 * @returns Formatted currency string with cents
 *
 * @example
 * formatCurrencyWithCents(1234.56) // '$1,234.56'
 */
export function formatCurrencyWithCents(
  amount: number | null | undefined,
  currency: string = 'USD'
): string {
  return formatCurrency(amount, currency, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

type DateFormat = 'short' | 'long' | 'relative';

/**
 * Format a date string or Date object
 *
 * @param date - The date to format (string or Date object)
 * @param format - The format type: 'short' (MM/DD/YYYY), 'long' (Month DD, YYYY), 'relative' (e.g., '2 days ago')
 * @returns Formatted date string
 *
 * @example
 * formatDate('2024-01-15', 'short') // '1/15/2024'
 * formatDate('2024-01-15', 'long') // 'January 15, 2024'
 * formatDate(new Date(), 'relative') // 'Today'
 */
export function formatDate(
  date: string | Date | null | undefined,
  format: DateFormat = 'short'
): string {
  if (!date) {
    return '-';
  }

  let dateObj: Date;
  try {
    dateObj = typeof date === 'string' ? new Date(date) : date;

    // Check for invalid date
    if (isNaN(dateObj.getTime())) {
      return typeof date === 'string' ? date : '-';
    }
  } catch {
    return typeof date === 'string' ? date : '-';
  }

  switch (format) {
    case 'short':
      return dateObj.toLocaleDateString('en-US', {
        month: 'numeric',
        day: 'numeric',
        year: 'numeric',
      });

    case 'long':
      return dateObj.toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
      });

    case 'relative':
      return formatRelativeDate(dateObj);

    default:
      return dateObj.toLocaleDateString();
  }
}

/**
 * Format a date as a relative time string
 *
 * @param date - The date to format
 * @returns Relative time string (e.g., 'Today', 'Yesterday', '3 days ago')
 */
function formatRelativeDate(date: Date): string {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const targetDate = new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate()
  );

  const diffTime = today.getTime() - targetDate.getTime();
  const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return 'Today';
  } else if (diffDays === 1) {
    return 'Yesterday';
  } else if (diffDays === -1) {
    return 'Tomorrow';
  } else if (diffDays > 1 && diffDays <= 7) {
    return `${diffDays} days ago`;
  } else if (diffDays < -1 && diffDays >= -7) {
    return `In ${Math.abs(diffDays)} days`;
  } else if (diffDays > 7 && diffDays <= 30) {
    const weeks = Math.round(diffDays / 7);
    return `${weeks} week${weeks > 1 ? 's' : ''} ago`;
  } else if (diffDays < -7 && diffDays >= -30) {
    const weeks = Math.round(Math.abs(diffDays) / 7);
    return `In ${weeks} week${weeks > 1 ? 's' : ''}`;
  } else {
    // Fallback to standard date format for dates outside 30 days
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  }
}

/**
 * Format a date with time
 *
 * @param date - The date to format
 * @param includeSeconds - Whether to include seconds (default: false)
 * @returns Formatted date and time string
 *
 * @example
 * formatDateTime('2024-01-15T14:30:00') // '1/15/2024, 2:30 PM'
 */
export function formatDateTime(
  date: string | Date | null | undefined,
  includeSeconds: boolean = false
): string {
  if (!date) {
    return '-';
  }

  let dateObj: Date;
  try {
    dateObj = typeof date === 'string' ? new Date(date) : date;

    if (isNaN(dateObj.getTime())) {
      return typeof date === 'string' ? date : '-';
    }
  } catch {
    return typeof date === 'string' ? date : '-';
  }

  return dateObj.toLocaleString('en-US', {
    month: 'numeric',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: includeSeconds ? '2-digit' : undefined,
    hour12: true,
  });
}

/**
 * Format a phone number for display
 *
 * @param phone - The phone number string
 * @returns Formatted phone number
 *
 * @example
 * formatPhoneNumber('1234567890') // '(123) 456-7890'
 * formatPhoneNumber('+11234567890') // '+1 (123) 456-7890'
 */
export function formatPhoneNumber(phone: string | null | undefined): string {
  if (!phone) {
    return '-';
  }

  // Remove all non-numeric characters except leading +
  const hasCountryCode = phone.startsWith('+');
  const cleaned = phone.replace(/\D/g, '');

  // Handle US/Canada numbers (10 or 11 digits)
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }

  if (cleaned.length === 11 && cleaned.startsWith('1')) {
    return `+1 (${cleaned.slice(1, 4)}) ${cleaned.slice(4, 7)}-${cleaned.slice(7)}`;
  }

  // For international numbers or other formats, return with original + if present
  if (hasCountryCode && cleaned.length > 10) {
    const countryCode = cleaned.slice(0, cleaned.length - 10);
    const number = cleaned.slice(-10);
    return `+${countryCode} (${number.slice(0, 3)}) ${number.slice(3, 6)}-${number.slice(6)}`;
  }

  // Return as-is if we can't determine the format
  return phone;
}

/**
 * Format a number as a percentage
 *
 * @param value - The numeric value (as a decimal or whole number)
 * @param decimals - Number of decimal places (default: 0)
 * @param isDecimal - Whether the input is already a decimal (e.g., 0.5 for 50%)
 * @returns Formatted percentage string
 *
 * @example
 * formatPercentage(75) // '75%'
 * formatPercentage(75.5, 1) // '75.5%'
 * formatPercentage(0.756, 1, true) // '75.6%'
 */
export function formatPercentage(
  value: number | null | undefined,
  decimals: number = 0,
  isDecimal: boolean = false
): string {
  if (value === null || value === undefined) {
    return '-';
  }

  const percentValue = isDecimal ? value * 100 : value;
  return `${percentValue.toFixed(decimals)}%`;
}

/**
 * Format a number with thousands separators
 *
 * @param value - The number to format
 * @param decimals - Number of decimal places (default: 0)
 * @returns Formatted number string
 *
 * @example
 * formatNumber(1234567) // '1,234,567'
 * formatNumber(1234.567, 2) // '1,234.57'
 */
export function formatNumber(
  value: number | null | undefined,
  decimals: number = 0
): string {
  if (value === null || value === undefined) {
    return '-';
  }

  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/**
 * Truncate a string to a maximum length with ellipsis
 *
 * @param text - The string to truncate
 * @param maxLength - Maximum length before truncation
 * @returns Truncated string with ellipsis if needed
 *
 * @example
 * truncateText('This is a very long string', 10) // 'This is a...'
 */
export function truncateText(
  text: string | null | undefined,
  maxLength: number
): string {
  if (!text) {
    return '';
  }

  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength)}...`;
}

/**
 * Capitalize the first letter of each word in a string
 *
 * @param text - The string to format
 * @returns Title-cased string
 *
 * @example
 * toTitleCase('hello world') // 'Hello World'
 */
export function toTitleCase(text: string | null | undefined): string {
  if (!text) {
    return '';
  }

  return text
    .toLowerCase()
    .split(' ')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

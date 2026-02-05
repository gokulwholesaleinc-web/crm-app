/**
 * Centralized utility exports
 */

// Status colors and styling
export {
  leadStatusColors,
  opportunityStatusColors,
  companyStatusColors,
  campaignStatusColors,
  getStatusColor,
  getStatusBadgeClasses,
  getStatusColorClasses,
  formatStatusLabel,
} from './statusColors';

export type { StatusType, StatusColorConfig } from './statusColors';

// Formatting utilities
export {
  formatCurrency,
  formatCurrencyWithCents,
  formatDate,
  formatDateTime,
  formatPhoneNumber,
  formatPercentage,
  formatNumber,
  truncateText,
  toTitleCase,
} from './formatters';

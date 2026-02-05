/**
 * Centralized status color mappings and utilities for consistent styling across the CRM application.
 */

export type StatusType = 'lead' | 'opportunity' | 'company' | 'campaign';

export interface StatusColorConfig {
  bg: string;
  text: string;
  border?: string;
}

/**
 * Lead status color mappings
 */
export const leadStatusColors: Record<string, StatusColorConfig> = {
  new: { bg: 'bg-blue-100', text: 'text-blue-800' },
  contacted: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
  qualified: { bg: 'bg-green-100', text: 'text-green-800' },
  proposal: { bg: 'bg-purple-100', text: 'text-purple-800' },
  negotiation: { bg: 'bg-orange-100', text: 'text-orange-800' },
  won: { bg: 'bg-emerald-100', text: 'text-emerald-800' },
  lost: { bg: 'bg-red-100', text: 'text-red-800' },
  unqualified: { bg: 'bg-red-100', text: 'text-red-800' },
  nurturing: { bg: 'bg-purple-100', text: 'text-purple-800' },
};

/**
 * Opportunity status/stage color mappings
 */
export const opportunityStatusColors: Record<string, StatusColorConfig> = {
  qualification: { bg: 'bg-blue-100', text: 'text-blue-800' },
  needs_analysis: { bg: 'bg-yellow-100', text: 'text-yellow-800' },
  proposal: { bg: 'bg-purple-100', text: 'text-purple-800' },
  negotiation: { bg: 'bg-orange-100', text: 'text-orange-800' },
  closed_won: { bg: 'bg-green-100', text: 'text-green-800' },
  closed_lost: { bg: 'bg-red-100', text: 'text-red-800' },
};

/**
 * Company status color mappings
 */
export const companyStatusColors: Record<string, StatusColorConfig> = {
  prospect: { bg: 'bg-blue-100', text: 'text-blue-800' },
  active: { bg: 'bg-green-100', text: 'text-green-800' },
  inactive: { bg: 'bg-gray-100', text: 'text-gray-800' },
  churned: { bg: 'bg-red-100', text: 'text-red-800' },
};

/**
 * Campaign status color mappings
 */
export const campaignStatusColors: Record<string, StatusColorConfig> = {
  draft: { bg: 'bg-gray-100', text: 'text-gray-700' },
  planned: { bg: 'bg-gray-100', text: 'text-gray-700' },
  scheduled: { bg: 'bg-blue-100', text: 'text-blue-700' },
  active: { bg: 'bg-green-100', text: 'text-green-700' },
  paused: { bg: 'bg-yellow-100', text: 'text-yellow-700' },
  completed: { bg: 'bg-blue-100', text: 'text-blue-700' },
};

/**
 * Default color configuration for unknown statuses
 */
const defaultStatusColor: StatusColorConfig = {
  bg: 'bg-gray-100',
  text: 'text-gray-800',
};

/**
 * Status color map by type
 */
const statusColorMap: Record<StatusType, Record<string, StatusColorConfig>> = {
  lead: leadStatusColors,
  opportunity: opportunityStatusColors,
  company: companyStatusColors,
  campaign: campaignStatusColors,
};

/**
 * Get the color configuration for a given status and type
 *
 * @param status - The status value (e.g., 'new', 'active', 'qualified')
 * @param type - The entity type ('lead', 'opportunity', 'company', 'campaign')
 * @returns StatusColorConfig object with bg and text color classes
 *
 * @example
 * const colors = getStatusColor('qualified', 'lead');
 * // { bg: 'bg-green-100', text: 'text-green-800' }
 */
export function getStatusColor(
  status: string,
  type: StatusType
): StatusColorConfig {
  const colorMap = statusColorMap[type];
  if (!colorMap) {
    return defaultStatusColor;
  }

  const normalizedStatus = status.toLowerCase().replace(/\s+/g, '_');
  return colorMap[normalizedStatus] ?? defaultStatusColor;
}

/**
 * Get Tailwind CSS classes for a status badge
 *
 * @param status - The status value
 * @param type - The entity type
 * @returns Combined Tailwind classes for badge styling
 *
 * @example
 * const classes = getStatusBadgeClasses('active', 'campaign');
 * // 'px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-700'
 */
export function getStatusBadgeClasses(
  status: string,
  type: StatusType
): string {
  const colors = getStatusColor(status, type);
  return `px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${colors.bg} ${colors.text}`;
}

/**
 * Get legacy format color classes (for backward compatibility with existing components)
 * Returns just the combined bg and text classes as a single string
 *
 * @param status - The status value
 * @param type - The entity type
 * @returns Combined bg and text Tailwind classes
 */
export function getStatusColorClasses(
  status: string,
  type: StatusType
): string {
  const colors = getStatusColor(status, type);
  return `${colors.bg} ${colors.text}`;
}

/**
 * Format a status string for display (capitalize first letter, replace underscores with spaces)
 *
 * @param status - The raw status string
 * @returns Formatted status string for display
 *
 * @example
 * formatStatusLabel('closed_won') // 'Closed won'
 */
export function formatStatusLabel(status: string): string {
  if (!status) return '';
  const formatted = status.replace(/_/g, ' ');
  return formatted.charAt(0).toUpperCase() + formatted.slice(1);
}

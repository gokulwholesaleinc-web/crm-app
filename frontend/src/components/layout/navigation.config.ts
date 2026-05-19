import { safeStorage } from '../../utils/safeStorage';
import {
  HomeIcon,
  UserGroupIcon,
  BuildingOfficeIcon,
  FunnelIcon,
  DocumentDuplicateIcon,
  CreditCardIcon,
  CalendarIcon,
  CalendarDaysIcon,
  MegaphoneIcon,
  ArrowsRightLeftIcon,
  ChartBarIcon,
  Cog6ToothIcon,
  ViewColumnsIcon,
  DocumentMagnifyingGlassIcon,
  ShieldCheckIcon,
  ClipboardDocumentListIcon,
  QuestionMarkCircleIcon,
  UserPlusIcon,
  ShareIcon,
  InboxIcon,
} from '@heroicons/react/24/outline';

export interface NavItem {
  id: string;
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string | number;
}

export const DEFAULT_MAIN_NAVIGATION: NavItem[] = [
  { id: 'dashboard', name: 'Dashboard', href: '/', icon: HomeIcon },
  { id: 'contacts', name: 'Contacts', href: '/contacts', icon: UserGroupIcon },
  { id: 'companies', name: 'Companies', href: '/companies', icon: BuildingOfficeIcon },
  { id: 'leads', name: 'Leads', href: '/leads', icon: FunnelIcon },
  { id: 'pipeline', name: 'Pipeline', href: '/pipeline', icon: ViewColumnsIcon },
  { id: 'inbox', name: 'Inbox', href: '/inbox', icon: InboxIcon },
  // Quotes nav entry removed 2026-05-14 — quotes replaced by one-off
  // Payment invoices with optional PDF attachments.
  { id: 'proposals', name: 'Proposals', href: '/proposals', icon: DocumentDuplicateIcon },
  // Contracts nav entry removed 2026-05-14 — contract terms now fold
  // into the Proposal T&C inline.
  { id: 'payments', name: 'Payments', href: '/payments', icon: CreditCardIcon },
  { id: 'activities', name: 'Activities', href: '/activities', icon: CalendarIcon },
  { id: 'calendar', name: 'Calendar', href: '/calendar', icon: CalendarDaysIcon },
  { id: 'campaigns', name: 'Email Campaigns', href: '/campaigns', icon: MegaphoneIcon },
];

export const DEFAULT_SECONDARY_NAVIGATION: NavItem[] = [
  { id: 'import-export', name: 'Import/Export', href: '/import-export', icon: ArrowsRightLeftIcon },
  { id: 'reports', name: 'Reports', href: '/reports', icon: ChartBarIcon },
  { id: 'settings', name: 'Settings', href: '/settings', icon: Cog6ToothIcon },
  { id: 'help', name: 'Help', href: '/help', icon: QuestionMarkCircleIcon },
  { id: 'admin', name: 'Admin', href: '/admin', icon: ShieldCheckIcon },
  { id: 'admin-audit', name: 'Audit', href: '/admin/audit', icon: ClipboardDocumentListIcon },
  { id: 'approvals', name: 'User Approvals', href: '/admin/user-approvals', icon: UserPlusIcon },
  { id: 'admin-sharing', name: 'Sharing', href: '/admin/sharing', icon: ShareIcon },
  { id: 'admin-dedup', name: 'Duplicate Cleanup', href: '/admin/dedup', icon: DocumentMagnifyingGlassIcon },
];

export const STORAGE_KEY_MAIN = 'crm-sidebar-order:v1';
export const STORAGE_KEY_SECONDARY = 'crm-sidebar-secondary-order:v1';

export const ADMIN_ONLY_IDS = new Set(['admin', 'admin-audit', 'approvals', 'admin-sharing', 'admin-dedup']);

export function readStoredOrder(key: string): string[] | null {
  const parsed = safeStorage.getJson<unknown>(key);
  if (Array.isArray(parsed) && parsed.every((id: unknown) => typeof id === 'string')) {
    return parsed as string[];
  }
  return null;
}

export function writeStoredOrder(key: string, ids: string[]): void {
  safeStorage.setJson(key, ids);
}

export function applyOrder(items: NavItem[], storedIds: string[] | null): NavItem[] {
  if (!storedIds) return items;
  const itemMap = new Map(items.map(item => [item.id, item]));
  const ordered: NavItem[] = [];
  for (const id of storedIds) {
    const item = itemMap.get(id);
    if (item) {
      ordered.push(item);
      itemMap.delete(id);
    }
  }
  for (const item of itemMap.values()) {
    ordered.push(item);
  }
  return ordered;
}

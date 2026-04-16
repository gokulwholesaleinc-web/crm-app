import {
  HomeIcon,
  UserGroupIcon,
  BuildingOfficeIcon,
  FunnelIcon,
  DocumentTextIcon,
  DocumentDuplicateIcon,
  CreditCardIcon,
  CalendarIcon,
  CalendarDaysIcon,
  MegaphoneIcon,
  BoltIcon,
  ArrowsRightLeftIcon,
  ChartBarIcon,
  SparklesIcon,
  Cog6ToothIcon,
  QueueListIcon,
  ViewColumnsIcon,
  DocumentMagnifyingGlassIcon,
  ShieldCheckIcon,
  QuestionMarkCircleIcon,
  UserPlusIcon,
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
  { id: 'quotes', name: 'Quotes', href: '/quotes', icon: DocumentTextIcon },
  { id: 'proposals', name: 'Proposals', href: '/proposals', icon: DocumentDuplicateIcon },
  { id: 'payments', name: 'Payments', href: '/payments', icon: CreditCardIcon },
  { id: 'activities', name: 'Activities', href: '/activities', icon: CalendarIcon },
  { id: 'calendar', name: 'Calendar', href: '/calendar', icon: CalendarDaysIcon },
  { id: 'campaigns', name: 'Campaigns', href: '/campaigns', icon: MegaphoneIcon },
];

export const DEFAULT_SECONDARY_NAVIGATION: NavItem[] = [
  { id: 'sequences', name: 'Sequences', href: '/sequences', icon: QueueListIcon },
  { id: 'workflows', name: 'Workflows', href: '/workflows', icon: BoltIcon },
  { id: 'duplicates', name: 'Duplicates', href: '/duplicates', icon: DocumentMagnifyingGlassIcon },
  { id: 'import-export', name: 'Import/Export', href: '/import-export', icon: ArrowsRightLeftIcon },
  { id: 'reports', name: 'Reports', href: '/reports', icon: ChartBarIcon },
  { id: 'ai-assistant', name: 'AI Assistant', href: '/ai-assistant', icon: SparklesIcon },
  { id: 'settings', name: 'Settings', href: '/settings', icon: Cog6ToothIcon },
  { id: 'help', name: 'Help', href: '/help', icon: QuestionMarkCircleIcon },
  { id: 'admin', name: 'Admin', href: '/admin', icon: ShieldCheckIcon },
  { id: 'approvals', name: 'User Approvals', href: '/admin/user-approvals', icon: UserPlusIcon },
];

export const STORAGE_KEY_MAIN = 'crm-sidebar-order:v1';
export const STORAGE_KEY_SECONDARY = 'crm-sidebar-secondary-order:v1';

export const ADMIN_ONLY_IDS = new Set(['admin', 'approvals']);

export function readStoredOrder(key: string): string[] | null {
  try {
    const stored = localStorage.getItem(key);
    if (stored) {
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed) && parsed.every((id: unknown) => typeof id === 'string')) {
        return parsed;
      }
    }
  } catch {
    // localStorage unavailable or corrupted data
  }
  return null;
}

export function writeStoredOrder(key: string, ids: string[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(ids));
  } catch {
    // localStorage unavailable or full
  }
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

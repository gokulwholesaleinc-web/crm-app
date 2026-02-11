import { useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import clsx from 'clsx';
import {
  HomeIcon,
  UserGroupIcon,
  BuildingOfficeIcon,
  FunnelIcon,
  CurrencyDollarIcon,
  DocumentTextIcon,
  DocumentDuplicateIcon,
  CalendarIcon,
  MegaphoneIcon,
  BoltIcon,
  ArrowsRightLeftIcon,
  ChartBarIcon,
  SparklesIcon,
  Cog6ToothIcon,
  XMarkIcon,
  QueueListIcon,
} from '@heroicons/react/24/outline';

export interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string | number;
}

const mainNavigation: NavItem[] = [
  { name: 'Dashboard', href: '/', icon: HomeIcon },
  { name: 'Contacts', href: '/contacts', icon: UserGroupIcon },
  { name: 'Companies', href: '/companies', icon: BuildingOfficeIcon },
  { name: 'Leads', href: '/leads', icon: FunnelIcon },
  { name: 'Opportunities', href: '/opportunities', icon: CurrencyDollarIcon },
  { name: 'Quotes', href: '/quotes', icon: DocumentTextIcon },
  { name: 'Proposals', href: '/proposals', icon: DocumentDuplicateIcon },
  { name: 'Activities', href: '/activities', icon: CalendarIcon },
  { name: 'Campaigns', href: '/campaigns', icon: MegaphoneIcon },
];

const secondaryNavigation: NavItem[] = [
  { name: 'Sequences', href: '/sequences', icon: QueueListIcon },
  { name: 'Workflows', href: '/workflows', icon: BoltIcon },
  { name: 'Import/Export', href: '/import-export', icon: ArrowsRightLeftIcon },
  { name: 'Reports', href: '/reports', icon: ChartBarIcon },
  { name: 'AI Assistant', href: '/ai-assistant', icon: SparklesIcon },
  { name: 'Settings', href: '/settings', icon: Cog6ToothIcon },
];

export interface SidebarProps {
  collapsed?: boolean;
  onCollapse?: (collapsed: boolean) => void;
  className?: string;
}

export function Sidebar({ collapsed = false, className }: SidebarProps) {
  const location = useLocation();

  const isActive = (href: string) => {
    if (href === '/') {
      return location.pathname === '/';
    }
    return location.pathname.startsWith(href);
  };

  const renderNavItem = (item: NavItem) => (
    <NavLink
      key={item.name}
      to={item.href}
      className={clsx(
        'group flex items-center rounded-lg transition-colors duration-200',
        collapsed ? 'px-3 py-3 justify-center' : 'px-3 py-2',
        isActive(item.href)
          ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400'
          : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-gray-100'
      )}
      title={collapsed ? item.name : undefined}
      aria-current={isActive(item.href) ? 'page' : undefined}
    >
      <item.icon
        className={clsx(
          'flex-shrink-0',
          collapsed ? 'h-6 w-6' : 'h-5 w-5 mr-3',
          isActive(item.href)
            ? 'text-primary-500 dark:text-primary-400'
            : 'text-gray-400 dark:text-gray-500 group-hover:text-gray-500 dark:group-hover:text-gray-400'
        )}
        aria-hidden="true"
      />
      {!collapsed && (
        <>
          <span className="flex-1 text-sm font-medium">{item.name}</span>
          {item.badge && (
            <span
              className={clsx(
                'ml-2 inline-flex items-center justify-center px-2 py-0.5 text-xs font-medium rounded-full',
                isActive(item.href)
                  ? 'bg-primary-100 text-primary-700'
                  : 'bg-gray-100 text-gray-600'
              )}
            >
              {item.badge}
            </span>
          )}
        </>
      )}
    </NavLink>
  );

  return (
    <aside
      className={clsx(
        'flex flex-col h-full bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 transition-[width] duration-200',
        collapsed ? 'w-16' : 'w-64',
        className
      )}
    >
      {/* Logo */}
      <div
        className={clsx(
          'flex items-center h-16 px-4 border-b border-gray-200 dark:border-gray-700',
          collapsed ? 'justify-center' : 'justify-start'
        )}
      >
        <div className="flex items-center">
          <div className="h-8 w-8 bg-primary-500 rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-lg">C</span>
          </div>
          {!collapsed && (
            <span className="ml-2 text-xl font-bold text-gray-900 dark:text-gray-100">CRM</span>
          )}
        </div>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto" aria-label="Main navigation">
        <div className="space-y-1">
          {mainNavigation.map(renderNavItem)}
        </div>

        {/* Divider */}
        <div className="my-4 border-t border-gray-200 dark:border-gray-700" />

        {/* Secondary Navigation */}
        <div className="space-y-1">
          {secondaryNavigation.map(renderNavItem)}
        </div>
      </nav>

      {/* Sidebar Footer */}
      {!collapsed && (
        <div className="px-4 py-4 border-t border-gray-200 dark:border-gray-700">
          <div className="text-xs text-gray-500 dark:text-gray-400">
            <p>CRM Application v1.0</p>
          </div>
        </div>
      )}
    </aside>
  );
}

// Shared navigation items for DRY principle - used by both Sidebar and MobileSidebar
export const getNavigation = () => ({
  main: mainNavigation,
  secondary: secondaryNavigation,
});

// Mobile Sidebar Overlay with proper animations and touch support
export interface MobileSidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function MobileSidebar({ isOpen, onClose }: MobileSidebarProps) {
  const location = useLocation();

  // Close sidebar on route change
  useEffect(() => {
    if (isOpen) {
      onClose();
    }
    // Only run when location changes, not when isOpen changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  // Handle escape key press
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  // Prevent body scroll when mobile menu is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  const isActive = (href: string) => {
    if (href === '/') {
      return location.pathname === '/';
    }
    return location.pathname.startsWith(href);
  };

  const renderMobileNavItem = (item: NavItem) => (
    <NavLink
      key={item.name}
      to={item.href}
      onClick={onClose}
      className={clsx(
        'group flex items-center px-3 py-3 rounded-lg transition-colors duration-200',
        'touch-manipulation', // Better touch handling
        isActive(item.href)
          ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400'
          : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-gray-100 active:bg-gray-200 dark:active:bg-gray-600'
      )}
    >
      <item.icon
        className={clsx(
          'flex-shrink-0 h-6 w-6 mr-3',
          isActive(item.href)
            ? 'text-primary-500 dark:text-primary-400'
            : 'text-gray-400 dark:text-gray-500 group-hover:text-gray-500 dark:group-hover:text-gray-400'
        )}
        aria-hidden="true"
      />
      <span className="flex-1 text-base font-medium">{item.name}</span>
      {item.badge && (
        <span
          className={clsx(
            'ml-2 inline-flex items-center justify-center px-2.5 py-1 text-xs font-medium rounded-full',
            isActive(item.href)
              ? 'bg-primary-100 text-primary-700'
              : 'bg-gray-100 text-gray-600'
          )}
        >
          {item.badge}
        </span>
      )}
    </NavLink>
  );

  return (
    <>
      {/* Backdrop with fade animation */}
      <div
        className={clsx(
          'fixed inset-0 z-40 bg-gray-600 transition-opacity duration-300 ease-in-out lg:hidden',
          isOpen ? 'opacity-75' : 'opacity-0 pointer-events-none'
        )}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Sidebar panel with slide animation */}
      <div
        className={clsx(
          'fixed inset-y-0 left-0 z-50 flex flex-col w-72 max-w-[85vw] bg-white dark:bg-gray-800 shadow-xl',
          'transform transition-transform duration-300 ease-in-out lg:hidden',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
        role="dialog"
        aria-modal="true"
        aria-label="Mobile navigation"
      >
        {/* Header with close button */}
        <div className="flex items-center justify-between h-16 px-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center">
            <div className="h-8 w-8 bg-primary-500 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-lg">C</span>
            </div>
            <span className="ml-2 text-xl font-bold text-gray-900 dark:text-gray-100">CRM</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 -mr-2 rounded-lg text-gray-400 hover:text-gray-500 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500 touch-manipulation"
            aria-label="Close sidebar"
          >
            <XMarkIcon className="h-6 w-6" aria-hidden="true" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto overscroll-contain" aria-label="Mobile navigation">
          <div className="space-y-1">
            {mainNavigation.map(renderMobileNavItem)}
          </div>

          {/* Divider */}
          <div className="my-4 border-t border-gray-200 dark:border-gray-700" />

          {/* Secondary Navigation */}
          <div className="space-y-1">
            {secondaryNavigation.map(renderMobileNavItem)}
          </div>
        </nav>

        {/* Footer */}
        <div className="px-4 py-4 border-t border-gray-200 dark:border-gray-700 safe-area-inset-bottom">
          <div className="text-xs text-gray-500 dark:text-gray-400">
            <p>CRM Application v1.0</p>
          </div>
        </div>
      </div>
    </>
  );
}

import { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import clsx from 'clsx';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { useTenant } from '../../providers/TenantProvider';
import { useAuthStore } from '../../store/authStore';
import {
  DEFAULT_MAIN_NAVIGATION,
  DEFAULT_SECONDARY_NAVIGATION,
  ADMIN_ONLY_IDS,
  type NavItem,
} from './navigation.config';

export interface MobileSidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function MobileSidebar({ isOpen, onClose }: MobileSidebarProps) {
  const location = useLocation();
  const { tenant } = useTenant();
  const [mobileLogoError, setMobileLogoError] = useState(false);
  const { user: mobileUser } = useAuthStore();

  useEffect(() => {
    setMobileLogoError(false);
  }, [tenant?.logo_url]);

  const isMobileAdmin = mobileUser?.is_superuser || mobileUser?.role === 'admin';
  const mobileSecondaryNav = isMobileAdmin
    ? DEFAULT_SECONDARY_NAVIGATION
    : DEFAULT_SECONDARY_NAVIGATION.filter(item => !ADMIN_ONLY_IDS.has(item.id));

  useEffect(() => {
    if (isOpen) {
      onClose();
    }
    // Only run when location changes, not when isOpen changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

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
      key={item.id}
      to={item.href}
      onClick={onClose}
      className={clsx(
        'group flex items-center px-3 py-3 rounded-lg transition-colors duration-200',
        'touch-manipulation',
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
      {item.badge != null && item.badge !== 0 && (
        <span
          className={clsx(
            'ml-2 inline-flex items-center justify-center px-2.5 py-1 text-xs font-medium rounded-full',
            isActive(item.href)
              ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
              : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
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
          <div className="flex items-center min-w-0">
            {tenant?.logo_url && !mobileLogoError ? (
              <img
                src={tenant.logo_url}
                alt={tenant.company_name || 'Logo'}
                width={32}
                height={32}
                className="h-8 w-8 rounded-lg object-contain flex-shrink-0"
                onError={() => setMobileLogoError(true)}
              />
            ) : (
              <div
                className={clsx(
                  'h-8 w-8 rounded-lg flex items-center justify-center flex-shrink-0',
                  !tenant?.primary_color && 'bg-primary-500'
                )}
                style={tenant?.primary_color ? { backgroundColor: tenant.primary_color } : undefined}
              >
                <span className="text-white font-bold text-lg">
                  {tenant?.company_name?.[0]?.toUpperCase() || 'C'}
                </span>
              </div>
            )}
            <span className="ml-2 text-xl font-bold text-gray-900 dark:text-gray-100 truncate">
              {tenant?.company_name || 'CRM'}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 -mr-2 rounded-lg text-gray-400 hover:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 dark:hover:text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 touch-manipulation"
            aria-label="Close sidebar"
          >
            <XMarkIcon className="h-6 w-6" aria-hidden="true" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto overscroll-contain" aria-label="Mobile navigation">
          <div className="space-y-1">
            {DEFAULT_MAIN_NAVIGATION.map(renderMobileNavItem)}
          </div>

          <div className="my-4 border-t border-gray-200 dark:border-gray-700" />

          <div className="space-y-1">
            {mobileSecondaryNav.map(renderMobileNavItem)}
          </div>
        </nav>

        {/* Footer */}
        <div className="px-4 py-4 border-t border-gray-200 dark:border-gray-700 safe-area-inset-bottom">
          <div className="text-xs text-gray-500 dark:text-gray-400">
            <p>{tenant?.footer_text || 'CRM Application v1.0'}</p>
          </div>
        </div>
      </div>
    </>
  );
}

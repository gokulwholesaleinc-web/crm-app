import { ReactNode, useState } from 'react';
import { Link } from 'react-router-dom';
import clsx from 'clsx';
import { Sidebar, MobileSidebar } from './Sidebar';
import { Header, User } from './Header';

export interface LayoutProps {
  children: ReactNode;
  user?: User;
  onLogout?: () => void;
  sidebarCollapsed?: boolean;
  onSidebarCollapse?: (collapsed: boolean) => void;
  showSearch?: boolean;
  notifications?: number;
  className?: string;
}

export function Layout({
  children,
  user,
  onLogout,
  sidebarCollapsed = false,
  onSidebarCollapse,
  showSearch = true,
  notifications = 0,
  className,
}: LayoutProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-900 overflow-hidden">
      {/* Skip Link */}
      <a href="#main-content" className="skip-link">Skip to main content</a>

      {/* Desktop Sidebar - hidden on mobile/tablet, visible on lg+ */}
      <div className="hidden lg:flex lg:flex-shrink-0">
        <Sidebar
          collapsed={sidebarCollapsed}
          onCollapse={onSidebarCollapse}
        />
      </div>

      {/* Mobile Sidebar Overlay - only renders on mobile/tablet */}
      <MobileSidebar
        isOpen={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
      />

      {/* Main Content Area - takes full width on mobile */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden w-full">
        <Header
          user={user}
          onMenuClick={() => setMobileMenuOpen(true)}
          onLogout={onLogout}
          showSearch={showSearch}
          notifications={notifications}
        />

        {/* Page Content - responsive padding */}
        <main
          id="main-content"
          className={clsx(
            'flex-1 overflow-y-auto focus:outline-none',
            className
          )}
        >
          <div className="py-4 sm:py-6">
            {/* Full width on mobile, constrained with responsive padding on larger screens */}
            <div className="w-full max-w-7xl mx-auto px-3 sm:px-6 lg:px-8">
              {children}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

// Page Header Component for consistent page titles
export interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  breadcrumbs?: Array<{ label: string; href?: string }>;
  className?: string;
}

export function PageHeader({
  title,
  description,
  actions,
  breadcrumbs,
  className,
}: PageHeaderProps) {
  return (
    <div className={clsx('mb-6', className)}>
      {/* Breadcrumbs */}
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav className="mb-2" aria-label="Breadcrumb">
          <ol className="flex items-center space-x-2 text-sm">
            {breadcrumbs.map((crumb, index) => (
              <li key={index} className="flex items-center">
                {index > 0 && (
                  <span className="mx-2 text-gray-400 dark:text-gray-500">/</span>
                )}
                {crumb.href ? (
                  <Link
                    to={crumb.href}
                    className="text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
                  >
                    {crumb.label}
                  </Link>
                ) : (
                  <span className="text-gray-900 dark:text-gray-100 font-medium">
                    {crumb.label}
                  </span>
                )}
              </li>
            ))}
          </ol>
        </nav>
      )}

      {/* Title and Actions - stacks on mobile, inline on larger screens */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100 truncate">
            {title}
          </h1>
          {description && (
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400 line-clamp-2 sm:line-clamp-1">
              {description}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex items-center space-x-2 sm:space-x-3 flex-shrink-0">
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}

// Content Container for consistent spacing
export interface ContentContainerProps {
  children: ReactNode;
  className?: string;
  fullWidth?: boolean;
}

export function ContentContainer({
  children,
  className,
  fullWidth = false,
}: ContentContainerProps) {
  return (
    <div
      className={clsx(
        fullWidth ? '' : 'max-w-7xl mx-auto',
        className
      )}
    >
      {children}
    </div>
  );
}

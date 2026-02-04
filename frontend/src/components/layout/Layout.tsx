import { ReactNode, useState } from 'react';
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
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      {/* Desktop Sidebar */}
      <div className="hidden lg:flex lg:flex-shrink-0">
        <Sidebar
          collapsed={sidebarCollapsed}
          onCollapse={onSidebarCollapse}
        />
      </div>

      {/* Mobile Sidebar */}
      <MobileSidebar
        isOpen={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
      />

      {/* Main Content */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Header
          user={user}
          onMenuClick={() => setMobileMenuOpen(true)}
          onLogout={onLogout}
          showSearch={showSearch}
          notifications={notifications}
        />

        {/* Page Content */}
        <main
          className={clsx(
            'flex-1 overflow-y-auto focus:outline-none',
            className
          )}
        >
          <div className="py-6">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
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
                  <span className="mx-2 text-gray-400">/</span>
                )}
                {crumb.href ? (
                  <a
                    href={crumb.href}
                    className="text-gray-500 hover:text-gray-700"
                  >
                    {crumb.label}
                  </a>
                ) : (
                  <span className="text-gray-900 font-medium">
                    {crumb.label}
                  </span>
                )}
              </li>
            ))}
          </ol>
        </nav>
      )}

      {/* Title and Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          {description && (
            <p className="mt-1 text-sm text-gray-500">{description}</p>
          )}
        </div>
        {actions && (
          <div className="mt-4 sm:mt-0 flex items-center space-x-3">
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

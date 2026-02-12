import { useEffect, useState, useCallback } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import clsx from 'clsx';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import type { DragEndEvent } from '@dnd-kit/core';
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
  arrayMove,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  HomeIcon,
  UserGroupIcon,
  BuildingOfficeIcon,
  FunnelIcon,
  CurrencyDollarIcon,
  DocumentTextIcon,
  DocumentDuplicateIcon,
  CreditCardIcon,
  CalendarIcon,
  MegaphoneIcon,
  BoltIcon,
  ArrowsRightLeftIcon,
  ChartBarIcon,
  SparklesIcon,
  Cog6ToothIcon,
  XMarkIcon,
  QueueListIcon,
  ViewColumnsIcon,
  DocumentMagnifyingGlassIcon,
  PencilSquareIcon,
  Bars2Icon,
  CheckIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';

export interface NavItem {
  id: string;
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string | number;
}

const DEFAULT_MAIN_NAVIGATION: NavItem[] = [
  { id: 'dashboard', name: 'Dashboard', href: '/', icon: HomeIcon },
  { id: 'contacts', name: 'Contacts', href: '/contacts', icon: UserGroupIcon },
  { id: 'companies', name: 'Companies', href: '/companies', icon: BuildingOfficeIcon },
  { id: 'leads', name: 'Leads', href: '/leads', icon: FunnelIcon },
  { id: 'opportunities', name: 'Opportunities', href: '/opportunities', icon: CurrencyDollarIcon },
  { id: 'pipeline', name: 'Pipeline', href: '/pipeline', icon: ViewColumnsIcon },
  { id: 'quotes', name: 'Quotes', href: '/quotes', icon: DocumentTextIcon },
  { id: 'proposals', name: 'Proposals', href: '/proposals', icon: DocumentDuplicateIcon },
  { id: 'payments', name: 'Payments', href: '/payments', icon: CreditCardIcon },
  { id: 'activities', name: 'Activities', href: '/activities', icon: CalendarIcon },
  { id: 'campaigns', name: 'Campaigns', href: '/campaigns', icon: MegaphoneIcon },
];

const DEFAULT_SECONDARY_NAVIGATION: NavItem[] = [
  { id: 'sequences', name: 'Sequences', href: '/sequences', icon: QueueListIcon },
  { id: 'workflows', name: 'Workflows', href: '/workflows', icon: BoltIcon },
  { id: 'duplicates', name: 'Duplicates', href: '/duplicates', icon: DocumentMagnifyingGlassIcon },
  { id: 'import-export', name: 'Import/Export', href: '/import-export', icon: ArrowsRightLeftIcon },
  { id: 'reports', name: 'Reports', href: '/reports', icon: ChartBarIcon },
  { id: 'ai-assistant', name: 'AI Assistant', href: '/ai-assistant', icon: SparklesIcon },
  { id: 'settings', name: 'Settings', href: '/settings', icon: Cog6ToothIcon },
];

const STORAGE_KEY_MAIN = 'crm-sidebar-order:v1';
const STORAGE_KEY_SECONDARY = 'crm-sidebar-secondary-order:v1';

function readStoredOrder(key: string): string[] | null {
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

function writeStoredOrder(key: string, ids: string[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(ids));
  } catch {
    // localStorage unavailable or full
  }
}

function applyOrder(items: NavItem[], storedIds: string[] | null): NavItem[] {
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

function StaticNavItem({
  item,
  collapsed,
  isActive,
}: {
  item: NavItem;
  collapsed: boolean;
  isActive: boolean;
}) {
  return (
    <NavLink
      to={item.href}
      className={clsx(
        'group flex items-center rounded-lg transition-colors duration-200',
        collapsed ? 'px-3 py-3 justify-center' : 'px-3 py-2',
        isActive
          ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400'
          : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-gray-100'
      )}
      title={collapsed ? item.name : undefined}
      aria-current={isActive ? 'page' : undefined}
    >
      <item.icon
        className={clsx(
          'flex-shrink-0',
          collapsed ? 'h-6 w-6' : 'h-5 w-5 mr-3',
          isActive
            ? 'text-primary-500 dark:text-primary-400'
            : 'text-gray-400 dark:text-gray-500 group-hover:text-gray-500 dark:group-hover:text-gray-400'
        )}
        aria-hidden="true"
      />
      {!collapsed && (
        <>
          <span className="flex-1 text-sm font-medium">{item.name}</span>
          {item.badge != null && item.badge !== 0 && (
            <span
              className={clsx(
                'ml-2 inline-flex items-center justify-center px-2 py-0.5 text-xs font-medium rounded-full',
                isActive
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
}

function SortableNavItem({
  item,
  collapsed,
  isActive,
}: {
  item: NavItem;
  collapsed: boolean;
  isActive: boolean;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: item.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={clsx(
        'group flex items-center rounded-lg transition-colors duration-200',
        collapsed ? 'px-3 py-3 justify-center' : 'px-3 py-2',
        isDragging
          ? 'bg-primary-50 dark:bg-primary-900/30 shadow-lg scale-[1.02] z-10 relative'
          : 'hover:bg-gray-50 dark:hover:bg-gray-700/50',
        !isDragging && isActive && 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400',
        !isDragging && !isActive && 'text-gray-700 dark:text-gray-300'
      )}
    >
      {!collapsed && (
        <button
          type="button"
          className="flex-shrink-0 mr-2 cursor-grab active:cursor-grabbing p-0.5 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          aria-label={`Reorder ${item.name}`}
          {...attributes}
          {...listeners}
        >
          <Bars2Icon className="h-4 w-4" aria-hidden="true" />
        </button>
      )}
      {collapsed && (
        <div
          className="cursor-grab active:cursor-grabbing"
          {...attributes}
          {...listeners}
        >
          <item.icon
            className={clsx(
              'flex-shrink-0 h-6 w-6',
              isActive
                ? 'text-primary-500 dark:text-primary-400'
                : 'text-gray-400 dark:text-gray-500'
            )}
            aria-hidden="true"
          />
        </div>
      )}
      {!collapsed && (
        <>
          <item.icon
            className={clsx(
              'flex-shrink-0 h-5 w-5 mr-3',
              isActive
                ? 'text-primary-500 dark:text-primary-400'
                : 'text-gray-400 dark:text-gray-500'
            )}
            aria-hidden="true"
          />
          <span className="flex-1 text-sm font-medium">{item.name}</span>
        </>
      )}
    </div>
  );
}

export interface SidebarProps {
  collapsed?: boolean;
  onCollapse?: (collapsed: boolean) => void;
  className?: string;
}

export function Sidebar({ collapsed = false, className }: SidebarProps) {
  const location = useLocation();
  const [editMode, setEditMode] = useState(false);

  const [mainNav, setMainNav] = useState<NavItem[]>(() =>
    applyOrder(DEFAULT_MAIN_NAVIGATION, readStoredOrder(STORAGE_KEY_MAIN))
  );
  const [secondaryNav, setSecondaryNav] = useState<NavItem[]>(() =>
    applyOrder(DEFAULT_SECONDARY_NAVIGATION, readStoredOrder(STORAGE_KEY_SECONDARY))
  );

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor)
  );

  const isActive = useCallback(
    (href: string) => {
      if (href === '/') {
        return location.pathname === '/';
      }
      return location.pathname.startsWith(href);
    },
    [location.pathname]
  );

  const handleMainDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    setMainNav(prev => {
      const oldIndex = prev.findIndex(item => item.id === active.id);
      const newIndex = prev.findIndex(item => item.id === over.id);
      const reordered = arrayMove(prev, oldIndex, newIndex);
      writeStoredOrder(STORAGE_KEY_MAIN, reordered.map(item => item.id));
      return reordered;
    });
  }, []);

  const handleSecondaryDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    setSecondaryNav(prev => {
      const oldIndex = prev.findIndex(item => item.id === active.id);
      const newIndex = prev.findIndex(item => item.id === over.id);
      const reordered = arrayMove(prev, oldIndex, newIndex);
      writeStoredOrder(STORAGE_KEY_SECONDARY, reordered.map(item => item.id));
      return reordered;
    });
  }, []);

  const handleResetOrder = useCallback(() => {
    setMainNav([...DEFAULT_MAIN_NAVIGATION]);
    setSecondaryNav([...DEFAULT_SECONDARY_NAVIGATION]);
    try {
      localStorage.removeItem(STORAGE_KEY_MAIN);
      localStorage.removeItem(STORAGE_KEY_SECONDARY);
    } catch {
      // localStorage unavailable
    }
  }, []);

  const mainIds = mainNav.map(item => item.id);
  const secondaryIds = secondaryNav.map(item => item.id);

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
        {/* Edit mode toggle */}
        {!collapsed && (
          <div className="flex items-center justify-end mb-2">
            <button
              type="button"
              onClick={() => setEditMode(prev => !prev)}
              className={clsx(
                'p-1.5 rounded-md transition-colors duration-150',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500',
                editMode
                  ? 'text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20'
                  : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
              )}
              aria-label={editMode ? 'Finish customizing menu' : 'Customize menu order'}
              title={editMode ? 'Done editing' : 'Customize order'}
            >
              {editMode ? (
                <CheckIcon className="h-4 w-4" aria-hidden="true" />
              ) : (
                <PencilSquareIcon className="h-4 w-4" aria-hidden="true" />
              )}
            </button>
          </div>
        )}

        {editMode ? (
          <>
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleMainDragEnd}
            >
              <SortableContext items={mainIds} strategy={verticalListSortingStrategy}>
                <div className="space-y-1">
                  {mainNav.map(item => (
                    <SortableNavItem
                      key={item.id}
                      item={item}
                      collapsed={collapsed}
                      isActive={isActive(item.href)}
                    />
                  ))}
                </div>
              </SortableContext>
            </DndContext>

            <div className="my-4 border-t border-gray-200 dark:border-gray-700" />

            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleSecondaryDragEnd}
            >
              <SortableContext items={secondaryIds} strategy={verticalListSortingStrategy}>
                <div className="space-y-1">
                  {secondaryNav.map(item => (
                    <SortableNavItem
                      key={item.id}
                      item={item}
                      collapsed={collapsed}
                      isActive={isActive(item.href)}
                    />
                  ))}
                </div>
              </SortableContext>
            </DndContext>

            {/* Edit mode actions */}
            {!collapsed && (
              <div className="mt-4 flex gap-2">
                <button
                  type="button"
                  onClick={handleResetOrder}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                >
                  <ArrowPathIcon className="h-3.5 w-3.5" aria-hidden="true" />
                  Reset to Default
                </button>
                <button
                  type="button"
                  onClick={() => setEditMode(false)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-primary-600 rounded-md hover:bg-primary-700 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                >
                  <CheckIcon className="h-3.5 w-3.5" aria-hidden="true" />
                  Done
                </button>
              </div>
            )}
          </>
        ) : (
          <>
            <div className="space-y-1">
              {mainNav.map(item => (
                <StaticNavItem
                  key={item.id}
                  item={item}
                  collapsed={collapsed}
                  isActive={isActive(item.href)}
                />
              ))}
            </div>

            <div className="my-4 border-t border-gray-200 dark:border-gray-700" />

            <div className="space-y-1">
              {secondaryNav.map(item => (
                <StaticNavItem
                  key={item.id}
                  item={item}
                  collapsed={collapsed}
                  isActive={isActive(item.href)}
                />
              ))}
            </div>
          </>
        )}
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
  main: DEFAULT_MAIN_NAVIGATION,
  secondary: DEFAULT_SECONDARY_NAVIGATION,
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
            {DEFAULT_MAIN_NAVIGATION.map(renderMobileNavItem)}
          </div>

          {/* Divider */}
          <div className="my-4 border-t border-gray-200 dark:border-gray-700" />

          {/* Secondary Navigation */}
          <div className="space-y-1">
            {DEFAULT_SECONDARY_NAVIGATION.map(renderMobileNavItem)}
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

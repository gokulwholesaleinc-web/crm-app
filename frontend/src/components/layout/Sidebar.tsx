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
  ArrowPathIcon,
  CheckIcon,
  PencilSquareIcon,
  Bars2Icon,
} from '@heroicons/react/24/outline';
import { useTenant } from '../../providers/TenantProvider';
import { useAuthStore } from '../../store/authStore';
import { safeStorage } from '../../utils/safeStorage';
import {
  DEFAULT_MAIN_NAVIGATION,
  DEFAULT_SECONDARY_NAVIGATION,
  STORAGE_KEY_MAIN,
  STORAGE_KEY_SECONDARY,
  ADMIN_ONLY_IDS,
  readStoredOrder,
  writeStoredOrder,
  applyOrder,
  type NavItem,
} from './navigation.config';

export type { NavItem };
export { DEFAULT_MAIN_NAVIGATION, DEFAULT_SECONDARY_NAVIGATION };

export { MobileSidebar } from './MobileSidebar';
export type { MobileSidebarProps } from './MobileSidebar';

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
                  ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
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
  const { tenant } = useTenant();
  const [editMode, setEditMode] = useState(false);
  const [logoError, setLogoError] = useState(false);

  useEffect(() => {
    setLogoError(false);
  }, [tenant?.logo_url]);

  const [mainNav, setMainNav] = useState<NavItem[]>(() =>
    applyOrder(DEFAULT_MAIN_NAVIGATION, readStoredOrder(STORAGE_KEY_MAIN))
  );
  const [secondaryNav, setSecondaryNav] = useState<NavItem[]>(() =>
    applyOrder(DEFAULT_SECONDARY_NAVIGATION, readStoredOrder(STORAGE_KEY_SECONDARY))
  );

  const { user } = useAuthStore();
  const isAdminUser = user?.is_superuser || user?.role === 'admin';
  const filteredSecondaryNav = isAdminUser
    ? secondaryNav
    : secondaryNav.filter(item => !ADMIN_ONLY_IDS.has(item.id));

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
    safeStorage.remove(STORAGE_KEY_MAIN);
    safeStorage.remove(STORAGE_KEY_SECONDARY);
  }, []);

  const mainIds = mainNav.map(item => item.id);
  const secondaryIds = filteredSecondaryNav.map(item => item.id);

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
        <div className="flex items-center min-w-0">
          {tenant?.logo_url && !logoError ? (
            <img
              src={tenant.logo_url}
              alt={tenant.company_name || 'Logo'}
              height={collapsed ? 32 : 40}
              className={clsx(
                'object-contain flex-shrink-0',
                collapsed ? 'h-8 w-auto max-w-[40px]' : 'h-10 w-auto max-w-[180px]'
              )}
              onError={() => setLogoError(true)}
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
          {!collapsed && (!tenant?.logo_url || logoError) && (
            <span className="ml-2 text-xl font-bold text-gray-900 dark:text-gray-100 truncate">
              {tenant?.company_name || 'CRM'}
            </span>
          )}
        </div>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto" aria-label="Main navigation">
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
                  {filteredSecondaryNav.map(item => (
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
              {filteredSecondaryNav.map(item => (
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
        <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700 space-y-2">
          <button
            type="button"
            onClick={() => setEditMode(prev => !prev)}
            className={clsx(
              'flex items-center gap-1.5 w-full text-xs rounded-md px-2 py-1.5 transition-colors duration-150',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500',
              editMode
                ? 'text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20 font-medium'
                : 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
            )}
            aria-label={editMode ? 'Finish customizing menu' : 'Customize menu order'}
          >
            {editMode ? (
              <>
                <CheckIcon className="h-3.5 w-3.5" aria-hidden="true" />
                Done Editing
              </>
            ) : (
              <>
                <PencilSquareIcon className="h-3.5 w-3.5" aria-hidden="true" />
                Customize Menu
              </>
            )}
          </button>
          <p className="text-xs text-gray-400 dark:text-gray-500">
            {tenant?.footer_text || 'CRM Application v1.0'}
          </p>
        </div>
      )}
    </aside>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export const getNavigation = () => ({
  main: DEFAULT_MAIN_NAVIGATION,
  secondary: DEFAULT_SECONDARY_NAVIGATION,
});

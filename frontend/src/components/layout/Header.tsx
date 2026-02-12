import { Fragment, useState, useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Menu, Transition } from '@headlessui/react';
import {
  Bars3Icon,
  BellIcon,
  MagnifyingGlassIcon,
  ChevronDownIcon,
  UserCircleIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
  XMarkIcon,
  SunIcon,
  MoonIcon,
} from '@heroicons/react/24/outline';
import clsx from 'clsx';
import { Avatar } from '../ui/Avatar';
import { useTheme } from '../../hooks/useTheme';

export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string | null;
}

export interface HeaderProps {
  user?: User;
  onMenuClick?: () => void;
  onSearch?: (query: string) => void;
  onLogout?: () => void;
  showSearch?: boolean;
  notifications?: number;
  className?: string;
}

export function Header({
  user,
  onMenuClick,
  onSearch,
  onLogout,
  showSearch = true,
  notifications = 0,
  className,
}: HeaderProps) {
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const { toggleTheme, isDark } = useTheme();

  // Focus search input when mobile search opens
  useEffect(() => {
    if (mobileSearchOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [mobileSearchOpen]);

  // Close mobile search on escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && mobileSearchOpen) {
        setMobileSearchOpen(false);
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [mobileSearchOpen]);

  return (
    <header
      className={clsx(
        'sticky top-0 z-30 flex items-center h-14 sm:h-16 px-3 sm:px-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700',
        className
      )}
    >
      {/* Mobile menu button (hamburger) */}
      <button
        type="button"
        className="lg:hidden p-2 -ml-1 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 focus-visible:outline-none focus:ring-2 focus:ring-primary-500 touch-manipulation"
        onClick={onMenuClick}
        aria-label="Open navigation menu"
      >
        <Bars3Icon className="h-6 w-6" aria-hidden="true" />
      </button>

      {/* Desktop Search */}
      {showSearch && (
        <div className="hidden sm:flex flex-1 max-w-md lg:max-w-lg ml-4 lg:ml-0">
          <div className="relative w-full">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <MagnifyingGlassIcon
                className="h-5 w-5 text-gray-400"
                aria-hidden="true"
              />
            </div>
            <input
              type="search"
              placeholder="Search contacts, companies, deals..."
              className="block w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg leading-5 bg-white dark:bg-gray-700 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 text-sm focus-visible:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              onChange={(e) => onSearch?.(e.target.value)}
            />
          </div>
        </div>
      )}

      {/* Mobile Search Toggle Button */}
      {showSearch && (
        <button
          type="button"
          className="sm:hidden ml-2 p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 focus-visible:outline-none focus:ring-2 focus:ring-primary-500 touch-manipulation"
          onClick={() => setMobileSearchOpen(true)}
          aria-label="Open search"
        >
          <MagnifyingGlassIcon className="h-5 w-5" aria-hidden="true" />
        </button>
      )}

      {/* Mobile Search Overlay */}
      {showSearch && mobileSearchOpen && (
        <div className="sm:hidden fixed inset-0 z-50 bg-white dark:bg-gray-800">
          <div className="flex items-center h-14 px-3 border-b border-gray-200 dark:border-gray-700">
            <div className="flex-1 relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <MagnifyingGlassIcon
                  className="h-5 w-5 text-gray-400"
                  aria-hidden="true"
                />
              </div>
              <input
                ref={searchInputRef}
                type="search"
                placeholder="Search..."
                className="block w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg leading-5 bg-white dark:bg-gray-700 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 text-base focus-visible:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                onChange={(e) => onSearch?.(e.target.value)}
              />
            </div>
            <button
              type="button"
              onClick={() => setMobileSearchOpen(false)}
              className="ml-2 p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 focus-visible:outline-none focus:ring-2 focus:ring-primary-500 touch-manipulation"
              aria-label="Close search"
            >
              <XMarkIcon className="h-6 w-6" aria-hidden="true" />
            </button>
          </div>
        </div>
      )}

      {/* Spacer for mobile to push right items */}
      <div className="flex-1 sm:hidden" />

      {/* Right side */}
      <div className="flex items-center ml-auto space-x-2 sm:space-x-4">
        {/* Theme Toggle */}
        <button
          type="button"
          className="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 focus-visible:outline-none focus:ring-2 focus:ring-primary-500 touch-manipulation"
          onClick={toggleTheme}
          aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {isDark ? (
            <SunIcon className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden="true" />
          ) : (
            <MoonIcon className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden="true" />
          )}
        </button>

        {/* Notifications */}
        <button
          type="button"
          className="relative p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 focus-visible:outline-none focus:ring-2 focus:ring-primary-500 touch-manipulation"
          aria-label="View notifications"
        >
          <BellIcon className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden="true" />
          {notifications > 0 && (
            <span className="absolute top-0.5 right-0.5 sm:top-1 sm:right-1 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 text-xs font-bold leading-none text-white bg-red-500 rounded-full">
              {notifications > 99 ? '99+' : notifications}
            </span>
          )}
        </button>

        {/* User Menu - touch-friendly with larger tap targets */}
        <Menu as="div" className="relative">
          <Menu.Button className="flex items-center p-1 sm:p-0 rounded-full text-sm focus-visible:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800 touch-manipulation">
            <span className="sr-only">Open user menu</span>
            <div className="flex items-center">
              <Avatar
                src={user?.avatar}
                name={user?.name}
                size="sm"
              />
              <div className="hidden md:flex md:items-center md:ml-2">
                <span className="text-sm font-medium text-gray-700 dark:text-gray-200 max-w-[120px] truncate">
                  {user?.name || 'User'}
                </span>
                <ChevronDownIcon
                  className="ml-1 h-4 w-4 text-gray-400"
                  aria-hidden="true"
                />
              </div>
            </div>
          </Menu.Button>
          <Transition
            as={Fragment}
            enter="transition ease-out duration-100"
            enterFrom="transform opacity-0 scale-95"
            enterTo="transform opacity-100 scale-100"
            leave="transition ease-in duration-75"
            leaveFrom="transform opacity-100 scale-100"
            leaveTo="transform opacity-0 scale-95"
          >
            <Menu.Items className="absolute right-0 z-50 mt-2 w-56 sm:w-48 origin-top-right rounded-lg bg-white dark:bg-gray-800 py-1 shadow-lg ring-1 ring-black ring-opacity-5 dark:ring-gray-700 focus-visible:outline-none">
              {user && (
                <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700">
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                    {user.name}
                  </p>
                  <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{user.email}</p>
                </div>
              )}
              <Menu.Item>
                {({ active }) => (
                  <Link
                    to="/profile"
                    className={clsx(
                      'flex items-center px-4 py-3 sm:py-2 text-sm touch-manipulation',
                      active ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300'
                    )}
                  >
                    <UserCircleIcon
                      className="mr-3 h-5 w-5 text-gray-400"
                      aria-hidden="true"
                    />
                    Your Profile
                  </Link>
                )}
              </Menu.Item>
              <Menu.Item>
                {({ active }) => (
                  <Link
                    to="/settings"
                    className={clsx(
                      'flex items-center px-4 py-3 sm:py-2 text-sm touch-manipulation',
                      active ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300'
                    )}
                  >
                    <Cog6ToothIcon
                      className="mr-3 h-5 w-5 text-gray-400"
                      aria-hidden="true"
                    />
                    Settings
                  </Link>
                )}
              </Menu.Item>
              <div className="border-t border-gray-100 dark:border-gray-700" />
              <Menu.Item>
                {({ active }) => (
                  <button
                    onClick={onLogout}
                    className={clsx(
                      'flex items-center w-full px-4 py-3 sm:py-2 text-sm text-left touch-manipulation',
                      active ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300'
                    )}
                  >
                    <ArrowRightOnRectangleIcon
                      className="mr-3 h-5 w-5 text-gray-400"
                      aria-hidden="true"
                    />
                    Sign out
                  </button>
                )}
              </Menu.Item>
            </Menu.Items>
          </Transition>
        </Menu>
      </div>
    </header>
  );
}

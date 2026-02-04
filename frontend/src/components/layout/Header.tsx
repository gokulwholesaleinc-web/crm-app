import { Fragment } from 'react';
import { Menu, Transition } from '@headlessui/react';
import {
  Bars3Icon,
  BellIcon,
  MagnifyingGlassIcon,
  ChevronDownIcon,
  UserCircleIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
} from '@heroicons/react/24/outline';
import clsx from 'clsx';
import { Avatar } from '../ui/Avatar';

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
  return (
    <header
      className={clsx(
        'sticky top-0 z-30 flex items-center h-16 px-4 bg-white border-b border-gray-200',
        className
      )}
    >
      {/* Mobile menu button */}
      <button
        type="button"
        className="lg:hidden p-2 rounded-md text-gray-400 hover:text-gray-500 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
        onClick={onMenuClick}
      >
        <span className="sr-only">Open sidebar</span>
        <Bars3Icon className="h-6 w-6" aria-hidden="true" />
      </button>

      {/* Search */}
      {showSearch && (
        <div className="flex-1 max-w-lg ml-4 lg:ml-0">
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <MagnifyingGlassIcon
                className="h-5 w-5 text-gray-400"
                aria-hidden="true"
              />
            </div>
            <input
              type="search"
              placeholder="Search contacts, companies, deals..."
              className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg leading-5 bg-white placeholder-gray-400 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              onChange={(e) => onSearch?.(e.target.value)}
            />
          </div>
        </div>
      )}

      {/* Right side */}
      <div className="flex items-center ml-auto space-x-4">
        {/* Notifications */}
        <button
          type="button"
          className="relative p-2 rounded-full text-gray-400 hover:text-gray-500 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <span className="sr-only">View notifications</span>
          <BellIcon className="h-6 w-6" aria-hidden="true" />
          {notifications > 0 && (
            <span className="absolute top-1 right-1 inline-flex items-center justify-center px-1.5 py-0.5 text-xs font-bold leading-none text-white transform translate-x-1/2 -translate-y-1/2 bg-red-500 rounded-full">
              {notifications > 99 ? '99+' : notifications}
            </span>
          )}
        </button>

        {/* User Menu */}
        <Menu as="div" className="relative">
          <Menu.Button className="flex items-center max-w-xs rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2">
            <span className="sr-only">Open user menu</span>
            <div className="flex items-center">
              <Avatar
                src={user?.avatar}
                name={user?.name}
                size="sm"
              />
              <div className="hidden md:flex md:items-center md:ml-2">
                <span className="text-sm font-medium text-gray-700">
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
            <Menu.Items className="absolute right-0 z-10 mt-2 w-48 origin-top-right rounded-lg bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none">
              {user && (
                <div className="px-4 py-3 border-b border-gray-100">
                  <p className="text-sm font-medium text-gray-900">
                    {user.name}
                  </p>
                  <p className="text-sm text-gray-500 truncate">{user.email}</p>
                </div>
              )}
              <Menu.Item>
                {({ active }) => (
                  <a
                    href="/profile"
                    className={clsx(
                      'flex items-center px-4 py-2 text-sm',
                      active ? 'bg-gray-100 text-gray-900' : 'text-gray-700'
                    )}
                  >
                    <UserCircleIcon
                      className="mr-3 h-5 w-5 text-gray-400"
                      aria-hidden="true"
                    />
                    Your Profile
                  </a>
                )}
              </Menu.Item>
              <Menu.Item>
                {({ active }) => (
                  <a
                    href="/settings"
                    className={clsx(
                      'flex items-center px-4 py-2 text-sm',
                      active ? 'bg-gray-100 text-gray-900' : 'text-gray-700'
                    )}
                  >
                    <Cog6ToothIcon
                      className="mr-3 h-5 w-5 text-gray-400"
                      aria-hidden="true"
                    />
                    Settings
                  </a>
                )}
              </Menu.Item>
              <div className="border-t border-gray-100" />
              <Menu.Item>
                {({ active }) => (
                  <button
                    onClick={onLogout}
                    className={clsx(
                      'flex items-center w-full px-4 py-2 text-sm text-left',
                      active ? 'bg-gray-100 text-gray-900' : 'text-gray-700'
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

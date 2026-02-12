import { Fragment, useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { BellIcon, CheckIcon } from '@heroicons/react/24/outline';
import { Transition } from '@headlessui/react';
import {
  useNotifications,
  useUnreadCount,
  useMarkNotificationRead,
  useMarkAllNotificationsRead,
} from '../../hooks/useNotifications';
import { Spinner } from '../ui/Spinner';

function getEntityRoute(entityType: string | null, entityId: number | null): string | null {
  if (!entityType || !entityId) return null;
  const routes: Record<string, string> = {
    contacts: `/contacts/${entityId}`,
    leads: `/leads/${entityId}`,
    opportunities: `/opportunities/${entityId}`,
    activities: `/activities`,
    companies: `/companies/${entityId}`,
  };
  return routes[entityType] ?? null;
}

function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();

  const { data: unreadData } = useUnreadCount();
  const { data: notificationsData, isLoading } = useNotifications({
    page: 1,
    page_size: 20,
  });
  const markReadMutation = useMarkNotificationRead();
  const markAllReadMutation = useMarkAllNotificationsRead();

  const unreadCount = unreadData?.count ?? 0;
  const notifications = notificationsData?.items ?? [];

  // Close panel on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        panelRef.current &&
        !panelRef.current.contains(event.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  // Close on Escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen]);

  const handleNotificationClick = (notification: {
    id: number;
    is_read: boolean;
    entity_type: string | null;
    entity_id: number | null;
  }) => {
    if (!notification.is_read) {
      markReadMutation.mutate(notification.id);
    }

    const route = getEntityRoute(notification.entity_type, notification.entity_id);
    if (route) {
      navigate(route);
      setIsOpen(false);
    }
  };

  const handleMarkAllRead = () => {
    markAllReadMutation.mutate();
  };

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        className="relative p-2 rounded-lg text-gray-500 hover:text-gray-600 hover:bg-gray-100 focus-visible:outline-none focus:ring-2 focus:ring-primary-500 touch-manipulation"
        onClick={() => setIsOpen(!isOpen)}
        aria-label="View notifications"
      >
        <BellIcon className="h-5 w-5 sm:h-6 sm:w-6" aria-hidden="true" />
        {unreadCount > 0 && (
          <span className="absolute top-0.5 right-0.5 sm:top-1 sm:right-1 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 text-xs font-bold leading-none text-white bg-red-500 rounded-full">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      <Transition
        show={isOpen}
        as={Fragment}
        enter="transition ease-out duration-100"
        enterFrom="transform opacity-0 scale-95"
        enterTo="transform opacity-100 scale-100"
        leave="transition ease-in duration-75"
        leaveFrom="transform opacity-100 scale-100"
        leaveTo="transform opacity-0 scale-95"
      >
        <div
          ref={panelRef}
          className="absolute right-0 z-50 mt-2 w-80 sm:w-96 origin-top-right rounded-lg bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus-visible:outline-none"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900">Notifications</h3>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={handleMarkAllRead}
                className="text-xs text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1"
                disabled={markAllReadMutation.isPending}
              >
                <CheckIcon className="h-3.5 w-3.5" aria-hidden="true" />
                Mark all read
              </button>
            )}
          </div>

          {/* Notifications list */}
          <div className="max-h-80 overflow-y-auto overscroll-contain">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Spinner size="sm" />
              </div>
            ) : notifications.length === 0 ? (
              <div className="py-8 text-center">
                <BellIcon className="mx-auto h-8 w-8 text-gray-300" aria-hidden="true" />
                <p className="mt-2 text-sm text-gray-500">No notifications yet</p>
              </div>
            ) : (
              <ul role="list">
                {notifications.map((notification) => (
                  <li key={notification.id}>
                    <button
                      type="button"
                      onClick={() => handleNotificationClick(notification)}
                      className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors ${
                        !notification.is_read ? 'bg-primary-50/50' : ''
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        {!notification.is_read && (
                          <span className="mt-1.5 h-2 w-2 rounded-full bg-primary-500 flex-shrink-0" />
                        )}
                        <div className={`min-w-0 flex-1 ${notification.is_read ? 'ml-5' : ''}`}>
                          <p className="text-sm font-medium text-gray-900 truncate">
                            {notification.title}
                          </p>
                          <p className="text-sm text-gray-600 line-clamp-2">
                            {notification.message}
                          </p>
                          <p className="text-xs text-gray-400 mt-1">
                            {formatTimeAgo(notification.created_at)}
                          </p>
                        </div>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Transition>
    </div>
  );
}

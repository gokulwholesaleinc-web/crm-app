/**
 * Central export for all Zustand stores.
 */

export {
  useAuthStore,
  selectUser,
  selectToken,
  selectIsAuthenticated,
  selectIsLoading,
  type User,
} from './authStore';

export {
  useUIStore,
  selectSidebarOpen,
  selectSidebarCollapsed,
  selectTheme,
  selectModal,
  selectToasts,
  selectGlobalLoading,
  selectCommandPaletteOpen,
  type Theme,
  type ModalState,
  type ToastMessage,
} from './uiStore';

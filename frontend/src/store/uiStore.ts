/**
 * Zustand store for UI state management.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export type Theme = 'light' | 'dark' | 'system';

export interface ModalState {
  isOpen: boolean;
  type: string | null;
  data?: Record<string, unknown>;
}

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message?: string;
  duration?: number;
}

interface UIState {
  // Sidebar
  sidebarOpen: boolean;
  sidebarCollapsed: boolean;

  // Theme
  theme: Theme;

  // Modals
  modals: Record<string, ModalState>;

  // Toasts
  toasts: ToastMessage[];

  // Global loading state
  globalLoading: boolean;

  // Command palette
  commandPaletteOpen: boolean;

  // Actions - Sidebar
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebarCollapsed: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;

  // Actions - Theme
  setTheme: (theme: Theme) => void;

  // Actions - Modals
  openModal: (modalId: string, type: string, data?: Record<string, unknown>) => void;
  closeModal: (modalId: string) => void;
  closeAllModals: () => void;

  // Actions - Toasts
  addToast: (toast: Omit<ToastMessage, 'id'>) => void;
  removeToast: (id: string) => void;
  clearToasts: () => void;

  // Actions - Global loading
  setGlobalLoading: (loading: boolean) => void;

  // Actions - Command palette
  toggleCommandPalette: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
}

// Utility to generate unique IDs
const generateId = () => Math.random().toString(36).substring(2, 9);

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      // Initial state
      sidebarOpen: true,
      sidebarCollapsed: false,
      theme: 'system',
      modals: {},
      toasts: [],
      globalLoading: false,
      commandPaletteOpen: false,

      // Sidebar actions
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
      toggleSidebarCollapsed: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),

      // Theme actions
      setTheme: (theme) => set({ theme }),

      // Modal actions
      openModal: (modalId, type, data) =>
        set((state) => ({
          modals: {
            ...state.modals,
            [modalId]: { isOpen: true, type, data },
          },
        })),

      closeModal: (modalId) =>
        set((state) => {
          const existingModal = state.modals[modalId];
          return {
            modals: {
              ...state.modals,
              [modalId]: existingModal
                ? { ...existingModal, isOpen: false }
                : { isOpen: false, type: null },
            },
          };
        }),

      closeAllModals: () =>
        set((state) => ({
          modals: Object.keys(state.modals).reduce(
            (acc, key) => ({
              ...acc,
              [key]: { ...state.modals[key], isOpen: false },
            }),
            {}
          ),
        })),

      // Toast actions
      addToast: (toast) =>
        set((state) => ({
          toasts: [...state.toasts, { ...toast, id: generateId() }],
        })),

      removeToast: (id) =>
        set((state) => ({
          toasts: state.toasts.filter((t) => t.id !== id),
        })),

      clearToasts: () => set({ toasts: [] }),

      // Global loading actions
      setGlobalLoading: (globalLoading) => set({ globalLoading }),

      // Command palette actions
      toggleCommandPalette: () =>
        set((state) => ({ commandPaletteOpen: !state.commandPaletteOpen })),
      setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),
    }),
    {
      name: 'crm-ui-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        theme: state.theme,
      }),
    }
  )
);

// Selectors
export const selectSidebarOpen = (state: UIState) => state.sidebarOpen;
export const selectSidebarCollapsed = (state: UIState) => state.sidebarCollapsed;
export const selectTheme = (state: UIState) => state.theme;
export const selectModal = (modalId: string) => (state: UIState) =>
  state.modals[modalId] || { isOpen: false, type: null };
export const selectToasts = (state: UIState) => state.toasts;
export const selectGlobalLoading = (state: UIState) => state.globalLoading;
export const selectCommandPaletteOpen = (state: UIState) => state.commandPaletteOpen;

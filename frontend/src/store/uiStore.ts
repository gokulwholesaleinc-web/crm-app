/**
 * Zustand store for UI state management.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface ModalState {
  isOpen: boolean;
  type: string | null;
  data?: Record<string, unknown>;
}

interface UIState {
  // Sidebar
  sidebarOpen: boolean;
  sidebarCollapsed: boolean;

  // Modals
  modals: Record<string, ModalState>;

  // Global loading state
  globalLoading: boolean;

  // Command palette
  commandPaletteOpen: boolean;

  // Actions - Sidebar
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebarCollapsed: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;

  // Actions - Modals
  openModal: (modalId: string, type: string, data?: Record<string, unknown>) => void;
  closeModal: (modalId: string) => void;
  closeAllModals: () => void;

  // Actions - Global loading
  setGlobalLoading: (loading: boolean) => void;

  // Actions - Command palette
  toggleCommandPalette: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      // Initial state
      sidebarOpen: true,
      sidebarCollapsed: false,
      modals: {},
      globalLoading: false,
      commandPaletteOpen: false,

      // Sidebar actions
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
      toggleSidebarCollapsed: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),

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
      }),
    }
  )
);

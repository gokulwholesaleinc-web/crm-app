/**
 * Main App component with routing, query client, and toast notifications.
 */

import { Suspense, useEffect, useRef } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';

import AppRoutes from './routes';
import { Spinner } from './components/ui/Spinner';
import { useAuthStore } from './store/authStore';
import { useTheme } from './hooks/useTheme';
import { TenantProvider, useTenant } from './providers/TenantProvider';
import { apiClient } from './api/client';

// Configure QueryClient with sensible defaults
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 10 * 60 * 1000, // 10 minutes (formerly cacheTime)
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});

// Loading fallback component for lazy-loaded routes
function PageLoader() {
  return (
    <div className="flex h-screen w-full items-center justify-center">
      <Spinner size="lg" />
    </div>
  );
}

// Component to handle auth events (401 responses)
function AuthEventHandler() {
  const logout = useAuthStore((state) => state.logout);

  useEffect(() => {
    const handleUnauthorized = () => {
      logout();
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => {
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    };
  }, [logout]);

  return null;
}

// Initialize theme at app root to prevent flash of wrong theme
function ThemeInitializer() {
  useTheme();
  return null;
}

// Recover tenant slug for already-authenticated users who are missing it.
// This handles users who logged in before the tenant-slug feature was
// deployed, or whose localStorage was cleared while the auth token persisted.
function TenantRecovery() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isLoading = useAuthStore((state) => state.isLoading);
  const { tenantSlug, setTenantSlug } = useTenant();
  const recovered = useRef(false);

  useEffect(() => {
    if (isLoading || !isAuthenticated || tenantSlug || recovered.current) {
      return;
    }
    recovered.current = true;

    // User is authenticated but has no tenant slug stored -- fetch their
    // tenant memberships from the backend and store the primary one.
    apiClient
      .get<Array<{ tenant_slug: string; is_primary: boolean }>>('/api/auth/me/tenants')
      .then((res) => {
        const tenants = res.data;
        if (tenants && tenants.length > 0) {
          const primary = tenants.find((t) => t.is_primary) ?? tenants[0];
          if (primary) {
            setTenantSlug(primary.tenant_slug);
          }
        }
      })
      .catch(() => {
        // Silently ignore -- user may genuinely have no tenant association,
        // or the token may be invalid (401 handler will redirect to login).
      });
  }, [isAuthenticated, isLoading, tenantSlug, setTenantSlug]);

  return null;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TenantProvider>
        <ThemeInitializer />
        <AuthEventHandler />
        <TenantRecovery />
        <BrowserRouter
          future={{
            v7_startTransition: true,
            v7_relativeSplatPath: true,
          }}
        >
          <Suspense fallback={<PageLoader />}>
            <AppRoutes />
          </Suspense>
          <div aria-live="polite" aria-atomic="true">
            <Toaster
              position="top-right"
              toastOptions={{
              duration: 4000,
              style: {
                background: '#363636',
                color: '#fff',
              },
              success: {
                duration: 3000,
                style: {
                  background: '#10B981',
                },
              },
              error: {
                duration: 5000,
                style: {
                  background: '#EF4444',
                },
              },
              }}
            />
          </div>
        </BrowserRouter>
      </TenantProvider>
    </QueryClientProvider>
  );
}

export default App;

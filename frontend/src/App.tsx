/**
 * Main App component with routing, query client, and toast notifications.
 */

import { Suspense, useEffect } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';

import AppRoutes from './routes';
import { Spinner } from './components/ui/Spinner';
import { useAuthStore } from './store/authStore';
import { useTheme } from './hooks/useTheme';
import { TenantProvider, useTenant } from './providers/TenantProvider';
import { apiClient } from './api/client';

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

function PageLoader() {
  return (
    <div className="flex h-screen w-full items-center justify-center">
      <Spinner size="lg" />
    </div>
  );
}

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

function ThemeInitializer() {
  useTheme();
  return null;
}

function TenantRecovery() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isLoading = useAuthStore((state) => state.isLoading);
  const { tenantSlug, setTenantSlug } = useTenant();

  useEffect(() => {
    if (isLoading || !isAuthenticated || tenantSlug) {
      return;
    }

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
        // ignore
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

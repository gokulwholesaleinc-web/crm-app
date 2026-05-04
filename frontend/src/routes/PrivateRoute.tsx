/**
 * Private route wrapper component.
 * Checks authentication status and redirects to login if not authenticated.
 * Wraps content in Layout component for consistent navigation.
 */

import { lazy, Suspense, useEffect, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import { useAuthStore } from '../store/authStore';
import { Spinner } from '../components/ui/Spinner';
import { Layout } from '../components/layout/Layout';
import { shouldShowWelcome } from '../features/onboarding/welcomeStorage';

const FloatingChatWidget = lazy(() => import('../components/ai/FloatingChatWidget').then(m => ({ default: m.FloatingChatWidget })));
const WelcomeModal = lazy(() => import('../features/onboarding/WelcomeModal').then(m => ({ default: m.WelcomeModal })));

interface PrivateRouteProps {
  children: React.ReactNode;
}

export function PrivateRoute({ children }: PrivateRouteProps) {
  const { isAuthenticated, isLoading, user, logout } = useAuthStore();
  const location = useLocation();
  const navigate = useNavigate();

  // Welcome modal: shown once per browser to authenticated users who
  // haven't dismissed it yet. The flag lives in localStorage; replay link
  // sits in /help so users can re-open it any time.
  const [welcomeOpen, setWelcomeOpen] = useState(false);
  useEffect(() => {
    if (isAuthenticated && shouldShowWelcome()) {
      setWelcomeOpen(true);
    }
  }, [isAuthenticated]);

  // Show loading spinner while checking auth state
  if (isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated) {
    // Save the attempted location for redirect after login
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Handle logout
  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  // Transform user data for Layout component
  const layoutUser = user
    ? {
        id: String(user.id),
        name: user.full_name,
        email: user.email,
        avatar: user.avatar_url,
      }
    : undefined;

  return (
    <Layout user={layoutUser} onLogout={handleLogout}>
      {children}
      <Suspense fallback={null}>
        <FloatingChatWidget />
      </Suspense>
      {welcomeOpen && (
        <Suspense fallback={null}>
          <WelcomeModal isOpen={welcomeOpen} onClose={() => setWelcomeOpen(false)} />
        </Suspense>
      )}
    </Layout>
  );
}

/**
 * Private route wrapper component.
 * Checks authentication status and redirects to login if not authenticated.
 */

import { Navigate, useLocation } from 'react-router-dom';

import { useAuthStore } from '../store/authStore';
import { Spinner } from '../components/ui/Spinner';

interface PrivateRouteProps {
  children: React.ReactNode;
}

export function PrivateRoute({ children }: PrivateRouteProps) {
  const { isAuthenticated, isLoading } = useAuthStore();
  const location = useLocation();

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

  return <>{children}</>;
}

export default PrivateRoute;

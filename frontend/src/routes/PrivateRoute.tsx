/**
 * Private route wrapper component.
 * Checks authentication status and redirects to login if not authenticated.
 * Wraps content in Layout component for consistent navigation.
 */

import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import { useAuthStore } from '../store/authStore';
import type { RoleName } from '../store/authStore';
import { Spinner } from '../components/ui/Spinner';
import { Layout } from '../components/layout/Layout';
import { EmptyState } from '../components/ui/EmptyState';
import { LockClosedIcon } from '@heroicons/react/24/outline';

interface PrivateRouteProps {
  children: React.ReactNode;
  allowedRoles?: RoleName[];
  allowSuperuser?: boolean;
}

export function PrivateRoute({
  children,
  allowedRoles,
  allowSuperuser = true,
}: PrivateRouteProps) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const location = useLocation();
  const navigate = useNavigate();

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

  const role = user?.role as RoleName | undefined;
  const isAllowed =
    !allowedRoles ||
    (allowSuperuser && user?.is_superuser === true) ||
    (role ? allowedRoles.includes(role) : false);

  return (
    <Layout user={layoutUser} onLogout={handleLogout}>
      {isAllowed ? (
        children
      ) : (
        <EmptyState
          variant="error"
          icon={<LockClosedIcon className="h-12 w-12" />}
          title="Access Denied"
          description="You do not have permission to view this page. If you believe this is a mistake, contact your workspace administrator."
          secondaryAction={{ label: 'Go to Dashboard', onClick: () => navigate('/') }}
        />
      )}
    </Layout>
  );
}

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { authApi } from '../../api/auth';
import { useAuthStore } from '../../store/authStore';
import { setTenantSlugOnLogin, useTenant } from '../../providers/TenantProvider';
import type { LoginRequest } from '../../types';

function LoginPage() {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const { login: storeLogin } = useAuthStore();
  const { tenant } = useTenant();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginRequest>({
    defaultValues: {
      email: '',
      password: '',
    },
  });

  const onSubmit = async (data: LoginRequest) => {
    setIsLoading(true);
    setError(null);

    try {
      // Use the auth API module which calls /api/auth/login/json
      const tokenResult = await authApi.login(data);

      // Get user profile after successful login
      const user = await authApi.getMe();

      // Save tenant slug from login response
      if (tokenResult.tenants && tokenResult.tenants.length > 0) {
        const primaryTenant = tokenResult.tenants.find(t => t.is_primary) ?? tokenResult.tenants[0];
        if (primaryTenant) {
          setTenantSlugOnLogin(primaryTenant.tenant_slug);
        }
      }

      // Update auth store with user and token
      storeLogin(user, tokenResult.access_token);

      navigate('/');
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message :
        (typeof err === 'object' && err !== null && 'detail' in err)
          ? String((err as { detail: unknown }).detail)
          : 'An error occurred';
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 py-8 sm:py-12 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-6 sm:space-y-8">
        <div>
          {tenant?.logo_url ? (
            <div className="flex justify-center mb-4">
              <img
                src={tenant.logo_url}
                alt={tenant.company_name || 'Company logo'}
                width={64}
                height={64}
                className="h-16 w-auto object-contain"
              />
            </div>
          ) : (
            <div className="flex justify-center mb-4">
              <div
                className="h-12 w-12 rounded-lg flex items-center justify-center"
                style={{ backgroundColor: tenant?.primary_color || '#6366f1' }}
              >
                <span className="text-white font-bold text-xl">
                  {tenant?.company_name?.[0]?.toUpperCase() || 'C'}
                </span>
              </div>
            </div>
          )}
          <h2 className="mt-4 sm:mt-6 text-center text-2xl sm:text-3xl font-extrabold text-gray-900 dark:text-gray-100">
            {tenant?.company_name ? `Sign in to ${tenant.company_name}` : 'Sign in to your account'}
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600 dark:text-gray-400">
            Or{' '}
            <Link
              to="/register"
              className="font-medium text-primary-600 hover:text-primary-500"
            >
              create a new account
            </Link>
          </p>
        </div>

        <form className="mt-6 sm:mt-8 space-y-4 sm:space-y-6" onSubmit={handleSubmit(onSubmit)}>
          {error && (
            <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-3 sm:p-4" role="alert" aria-live="polite">
              <div className="flex">
                <div className="ml-3">
                  <h3 className="text-sm font-medium text-red-800 dark:text-red-300">{error}</h3>
                </div>
              </div>
            </div>
          )}

          <div className="rounded-md shadow-sm -space-y-px">
            <div>
              <label htmlFor="email" className="sr-only">
                Email address
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                spellCheck={false}
                {...register('email', {
                  required: 'Email is required',
                  pattern: {
                    value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i,
                    message: 'Invalid email address',
                  },
                })}
                className="appearance-none rounded-none relative block w-full px-3 py-2.5 sm:py-2 border border-gray-300 dark:border-gray-600 placeholder-gray-500 dark:placeholder-gray-400 text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 text-base sm:text-sm rounded-t-md focus-visible:outline-none focus-visible:ring-primary-500 focus-visible:border-primary-500 focus-visible:z-10"
                placeholder="Email address"
              />
              {errors.email && (
                <p className="mt-1 text-xs sm:text-sm text-red-600 dark:text-red-400">{errors.email.message}</p>
              )}
            </div>
            <div className="relative">
              <label htmlFor="password" className="sr-only">
                Password
              </label>
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                {...register('password', {
                  required: 'Password is required',
                })}
                className="appearance-none rounded-none relative block w-full px-3 py-2.5 sm:py-2 pr-10 border border-gray-300 dark:border-gray-600 placeholder-gray-500 dark:placeholder-gray-400 text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 text-base sm:text-sm rounded-b-md focus-visible:outline-none focus-visible:ring-primary-500 focus-visible:border-primary-500 focus-visible:z-10"
                placeholder="Password"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
                className="absolute top-1/2 -translate-y-1/2 right-0 pr-3 flex items-center justify-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus-visible:outline-none focus-visible:text-gray-600 dark:focus-visible:text-gray-300 z-10 cursor-pointer"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? (
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                  </svg>
                ) : (
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                )}
              </button>
              {errors.password && (
                <p className="mt-1 text-xs sm:text-sm text-red-600 dark:text-red-400">{errors.password.message}</p>
              )}
            </div>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between space-y-3 sm:space-y-0">
            <div className="flex items-center">
              <input
                id="remember-me"
                name="remember-me"
                type="checkbox"
                className="h-4 w-4 text-primary-600 focus-visible:ring-primary-500 border-gray-300 rounded"
              />
              <label htmlFor="remember-me" className="ml-2 block text-sm text-gray-900 dark:text-gray-300">
                Remember me
              </label>
            </div>

            <div className="text-sm">
              <Link to="/forgot-password" className="font-medium text-primary-600 hover:text-primary-500">
                Forgot your password?
              </Link>
            </div>
          </div>

          <div>
            <Button type="submit" fullWidth isLoading={isLoading} size="lg" className="sm:text-sm sm:py-2">
              Sign in
            </Button>
          </div>
        </form>

      </div>
    </div>
  );
}

export default LoginPage;

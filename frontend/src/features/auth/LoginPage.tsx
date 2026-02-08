import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { authApi } from '../../api/auth';
import { useAuthStore } from '../../store/authStore';
import type { LoginRequest } from '../../types';

function LoginPage() {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { login: storeLogin } = useAuthStore();

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<LoginRequest>({
    defaultValues: {
      email: '',
      password: '',
    },
  });

  const fillDemoAccount = (email: string, password: string) => {
    setValue('email', email);
    setValue('password', password);
  };

  const onSubmit = async (data: LoginRequest) => {
    setIsLoading(true);
    setError(null);

    try {
      // Use the auth API module which calls /api/auth/login/json
      const tokenResult = await authApi.login(data);

      // Get user profile after successful login
      const user = await authApi.getMe();

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
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-8 sm:py-12 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-6 sm:space-y-8">
        <div>
          <h2 className="mt-4 sm:mt-6 text-center text-2xl sm:text-3xl font-extrabold text-gray-900">
            Sign in to your account
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
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
            <div className="rounded-md bg-red-50 p-3 sm:p-4">
              <div className="flex">
                <div className="ml-3">
                  <h3 className="text-sm font-medium text-red-800">{error}</h3>
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
                {...register('email', {
                  required: 'Email is required',
                  pattern: {
                    value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i,
                    message: 'Invalid email address',
                  },
                })}
                className="appearance-none rounded-none relative block w-full px-3 py-2.5 sm:py-2 border border-gray-300 placeholder-gray-500 text-gray-900 text-base sm:text-sm rounded-t-md focus:outline-none focus:ring-primary-500 focus:border-primary-500 focus:z-10"
                placeholder="Email address"
              />
              {errors.email && (
                <p className="mt-1 text-xs sm:text-sm text-red-600">{errors.email.message}</p>
              )}
            </div>
            <div>
              <label htmlFor="password" className="sr-only">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                {...register('password', {
                  required: 'Password is required',
                })}
                className="appearance-none rounded-none relative block w-full px-3 py-2.5 sm:py-2 border border-gray-300 placeholder-gray-500 text-gray-900 text-base sm:text-sm rounded-b-md focus:outline-none focus:ring-primary-500 focus:border-primary-500 focus:z-10"
                placeholder="Password"
              />
              {errors.password && (
                <p className="mt-1 text-xs sm:text-sm text-red-600">{errors.password.message}</p>
              )}
            </div>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between space-y-3 sm:space-y-0">
            <div className="flex items-center">
              <input
                id="remember-me"
                name="remember-me"
                type="checkbox"
                className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
              />
              <label htmlFor="remember-me" className="ml-2 block text-sm text-gray-900">
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

        <div className="border-t border-gray-200 pt-4">
          <p className="text-xs text-gray-400 text-center mb-3">Demo Accounts</p>
          <div className="flex flex-col sm:flex-row gap-2">
            <button
              type="button"
              onClick={() => fillDemoAccount('demo@demo.com', 'demo123')}
              className="flex-1 text-xs px-3 py-2 border border-gray-200 rounded-md text-gray-500 hover:bg-gray-50 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors"
            >
              Demo User (sample data)
            </button>
            <button
              type="button"
              onClick={() => fillDemoAccount('admin@admin.com', 'admin123')}
              className="flex-1 text-xs px-3 py-2 border border-gray-200 rounded-md text-gray-500 hover:bg-gray-50 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors"
            >
              Admin (clean account)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;

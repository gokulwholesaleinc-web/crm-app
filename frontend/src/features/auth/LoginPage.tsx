import { useEffect, useState } from 'react';
import { useTenant } from '../../providers/TenantProvider';
import { safeStorage } from '../../utils/safeStorage';
import GoogleSignInButton from './GoogleSignInButton';

function LoginPage() {
  const [error, setError] = useState<string | null>(null);
  const { tenant } = useTenant();
  const [logoError, setLogoError] = useState(false);

  useEffect(() => {
    setLogoError(false);
  }, [tenant?.logo_url]);

  useEffect(() => {
    safeStorage.remove('crm-remember:v1');
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 py-8 sm:py-12 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-6 sm:space-y-8">
        <div>
          {tenant?.logo_url && !logoError ? (
            <div className="flex justify-center mb-4">
              <img
                src={tenant.logo_url}
                alt={tenant.company_name || 'Company logo'}
                width={64}
                height={64}
                className="h-16 w-auto object-contain"
                onError={() => setLogoError(true)}
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
          <p className="mt-2 text-center text-sm text-gray-500 dark:text-gray-400">
            Sign in with your Google account to continue.
          </p>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-3 sm:p-4" role="alert" aria-live="polite">
            <h3 className="text-sm font-medium text-red-800 dark:text-red-300">{error}</h3>
          </div>
        )}

        <GoogleSignInButton onError={setError} />
      </div>
    </div>
  );
}

export default LoginPage;

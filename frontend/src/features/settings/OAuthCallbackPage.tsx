import { useEffect, useRef } from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { Spinner } from '../../components/ui/Spinner';
import { showSuccess, showError } from '../../utils/toast';
import { calendarCallback, metaCallback } from '../../api/integrations';

function OAuthCallbackPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;

    const code = searchParams.get('code');
    if (!code) {
      showError('Missing authorization code');
      navigate('/settings', { replace: true });
      return;
    }

    const isGoogle = location.pathname.includes('google-calendar');
    const isMeta = location.pathname.includes('meta');

    (async () => {
      try {
        if (isGoogle) {
          await calendarCallback(code);
          showSuccess('Google Calendar connected successfully');
        } else if (isMeta) {
          const redirectUri = window.location.origin + '/settings/integrations/meta/callback';
          await metaCallback(code, redirectUri);
          showSuccess('Meta connected successfully');
        } else {
          showError('Unknown integration callback');
        }
      } catch {
        showError('Failed to complete connection. Please try again.');
      } finally {
        navigate('/settings', { replace: true });
      }
    })();
  }, [searchParams, location.pathname, navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <Spinner size="lg" className="mx-auto mb-4 text-blue-600" />
        <p className="text-gray-600">Completing connection...</p>
      </div>
    </div>
  );
}

export default OAuthCallbackPage;

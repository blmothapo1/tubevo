// filepath: frontend/src/pages/GoogleCallback.jsx
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../lib/api';
import Spinner from '../components/Spinner';

/**
 * Google OAuth callback page.
 *
 * Google redirects here with ?code=...&state=...
 * We POST the code to the backend, which exchanges it for tokens.
 * Then we redirect to /settings (YouTube tab).
 */
export default function GoogleCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState('connecting'); // connecting | success | error
  const [error, setError] = useState('');

  useEffect(() => {
    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const errorParam = searchParams.get('error');

    if (errorParam) {
      setStatus('error');
      setError(
        errorParam === 'access_denied'
          ? 'You denied access. Please try again from Settings.'
          : `Google returned an error: ${errorParam}`
      );
      return;
    }

    if (!code) {
      setStatus('error');
      setError('No authorization code received from Google.');
      return;
    }

    async function exchangeCode() {
      try {
        await api.post('/oauth/youtube/callback', { code, state });
        setStatus('success');
        // Check if the user connected from onboarding vs settings
        const origin = localStorage.getItem('yt_connect_origin');
        localStorage.removeItem('yt_connect_origin');
        const redirectTo = origin === 'onboarding' ? '/onboarding' : '/settings?tab=youtube';
        // Brief pause so the user sees the success message
        setTimeout(() => navigate(redirectTo, { replace: true }), 1500);
      } catch (err) {
        setStatus('error');
        setError(
          err.response?.data?.detail ||
            'Failed to connect your YouTube account. Please try again.'
        );
      }
    }

    exchangeCode();
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-50">
      <div className="bg-surface-100 border border-surface-300 rounded-2xl p-8 max-w-md w-full text-center space-y-4">
        {status === 'connecting' && (
          <>
            <Spinner className="w-8 h-8 mx-auto text-brand-500" />
            <h2 className="text-lg font-semibold text-white">Connecting YouTube…</h2>
            <p className="text-sm text-surface-700">
              Please wait while we link your Google account.
            </p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="w-12 h-12 mx-auto rounded-full bg-emerald-500/15 flex items-center justify-center">
              <svg className="w-6 h-6 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-white">YouTube Connected!</h2>
            <p className="text-sm text-surface-700">
              Redirecting you to Settings…
            </p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="w-12 h-12 mx-auto rounded-full bg-red-500/15 flex items-center justify-center">
              <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-white">Connection Failed</h2>
            <p className="text-sm text-red-400">{error}</p>
            <button
              onClick={() => navigate('/settings?tab=youtube', { replace: true })}
              className="mt-4 px-5 py-2.5 rounded-lg text-sm font-medium bg-surface-300 text-surface-800 hover:bg-surface-400 transition-colors"
            >
              Back to Settings
            </button>
          </>
        )}
      </div>
    </div>
  );
}

import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api, { setTokens } from '../lib/api';

export default function AppleCallback() {
  const navigate = useNavigate();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    if (code) {
      api.post('/auth/apple', { code })
        .then(({ data }) => {
          setTokens(data.access_token, data.refresh_token);
          navigate('/dashboard');
        })
        .catch(() => {
          navigate('/login?error=apple');
        });
    } else {
      navigate('/login?error=apple');
    }
  }, [navigate]);

  return <div className="flex items-center justify-center min-h-screen text-[14px] text-surface-700">Signing in with Apple…</div>;
}

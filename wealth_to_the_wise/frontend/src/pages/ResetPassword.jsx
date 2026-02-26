import { useState } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import api from '../lib/api';
import Spinner from '../components/Spinner';
import tubevoLogo from '../assets/tubevo-logo-web.png';

const ease = [0.25, 0.1, 0.25, 1];

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token') || '';

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (!token) {
      setError('Missing reset token. Please use the link from your email.');
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/reset-password', {
        token,
        new_password: password,
      });
      setSuccess(true);
      // Auto-redirect to login after 3 seconds
      setTimeout(() => navigate('/login'), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to reset password. The link may have expired.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-surface-50 flex items-center justify-center px-5 relative overflow-hidden">
      {/* Ambient background */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[500px] h-[350px] bg-brand-600/4 rounded-full blur-[100px] pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease }}
        className="w-full max-w-[380px] relative z-10"
      >
        <div className="text-center mb-8">
          <Link to="/">
            <img src={tubevoLogo} alt="Tubevo" className="h-8 mx-auto" />
          </Link>
          <p className="mt-2.5 text-xs text-surface-600 uppercase tracking-wider font-medium">Choose a new password</p>
        </div>

        {success ? (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="card p-6 text-center space-y-3"
          >
            <div className="w-10 h-10 rounded bg-green-500/10 flex items-center justify-center mx-auto">
              <svg className="w-5 h-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h3 className="text-sm font-semibold text-white">Password reset!</h3>
            <p className="text-xs text-surface-600">
              Your password has been updated. Redirecting to login…
            </p>
            <Link
              to="/login"
              className="inline-block text-xs text-brand-400 hover:text-brand-300 font-medium transition-colors mt-1"
            >
              Go to login now →
            </Link>
          </motion.div>
        ) : (
          <form onSubmit={handleSubmit} className="card p-6 space-y-4">
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-red-500/6 text-red-400 text-xs px-3 py-2.5 rounded-lg"
              >
                {error}
              </motion.div>
            )}

            {!token && (
              <div className="bg-yellow-500/6 text-yellow-400 text-xs px-3 py-2.5 rounded-lg">
                No reset token found. Please use the link from your email.
              </div>
            )}

            <div>
              <label className="block text-[10px] font-semibold text-surface-600 mb-1.5 uppercase tracking-wider">New password</label>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-premium"
                placeholder="••••••••"
              />
            </div>

            <div>
              <label className="block text-[10px] font-semibold text-surface-600 mb-1.5 uppercase tracking-wider">Confirm password</label>
              <input
                type="password"
                required
                minLength={8}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="input-premium"
                placeholder="••••••••"
              />
            </div>

            <motion.button
              type="submit"
              disabled={loading || !token}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              className="btn-primary w-full !py-2.5"
            >
              {loading ? <Spinner className="w-4 h-4" /> : 'Reset password'}
            </motion.button>
          </form>
        )}

        <p className="text-center text-xs text-surface-600 mt-6">
          <Link to="/login" className="text-brand-400 hover:text-brand-300 font-medium transition-colors duration-150">
            ← Back to login
          </Link>
        </p>
      </motion.div>
    </div>
  );
}

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
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-brand-600/6 rounded-full blur-[100px] pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease }}
        className="w-full max-w-[400px] relative z-10"
      >
        <div className="text-center mb-10">
          <Link to="/">
            <img src={tubevoLogo} alt="Tubevo" className="h-9 mx-auto" />
          </Link>
          <p className="mt-3 text-sm text-surface-600">Choose a new password</p>
        </div>

        {success ? (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="card-elevated p-7 text-center space-y-4"
          >
            <div className="w-12 h-12 rounded-xl bg-green-500/15 flex items-center justify-center mx-auto">
              <svg className="w-6 h-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-white">Password reset!</h3>
            <p className="text-sm text-surface-600">
              Your password has been updated. Redirecting to login…
            </p>
            <Link
              to="/login"
              className="inline-block text-sm text-brand-400 hover:text-brand-300 font-medium transition-colors mt-2"
            >
              Go to login now →
            </Link>
          </motion.div>
        ) : (
          <form onSubmit={handleSubmit} className="card-elevated p-7 space-y-5">
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-red-500/8 border border-red-500/15 text-red-400 text-sm px-4 py-3 rounded-xl"
              >
                {error}
              </motion.div>
            )}

            {!token && (
              <div className="bg-yellow-500/8 border border-yellow-500/15 text-yellow-400 text-sm px-4 py-3 rounded-xl">
                No reset token found. Please use the link from your email.
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-surface-700 mb-2">New password</label>
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
              <label className="block text-xs font-medium text-surface-700 mb-2">Confirm password</label>
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
              whileTap={{ scale: 0.98 }}
              className="btn-primary w-full !py-3"
            >
              {loading ? <Spinner className="w-4 h-4" /> : 'Reset password'}
            </motion.button>
          </form>
        )}

        <p className="text-center text-sm text-surface-600 mt-7">
          <Link to="/login" className="text-brand-400 hover:text-brand-300 font-medium transition-colors duration-200">
            ← Back to login
          </Link>
        </p>
      </motion.div>
    </div>
  );
}

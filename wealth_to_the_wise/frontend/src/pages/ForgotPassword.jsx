import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import api from '../lib/api';
import Spinner from '../components/Spinner';
import tubevoLogo from '../assets/tubevo-logo-web.png';

const ease = [0.25, 0.1, 0.25, 1];

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await api.post('/auth/forgot-password', { email });
      setSent(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Something went wrong. Please try again.');
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
          <p className="mt-2.5 text-xs text-surface-600 uppercase tracking-wider font-medium">Reset your password</p>
        </div>

        {sent ? (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="card p-6 text-center space-y-3"
          >
            <div className="w-10 h-10 rounded bg-brand-500/10 flex items-center justify-center mx-auto">
              <svg className="w-5 h-5 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <h3 className="text-sm font-semibold text-white">Check your email</h3>
            <p className="text-xs text-surface-600">
              If an account exists for <strong className="text-surface-800">{email}</strong>,
              we've sent a reset link. Expires in 1 hour.
            </p>
            <Link
              to="/login"
              className="inline-block text-xs text-brand-400 hover:text-brand-300 font-medium transition-colors mt-1"
            >
              ← Back to login
            </Link>
          </motion.div>
        ) : (
          <form onSubmit={handleSubmit} className="card p-6 space-y-4">
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-red-500/6 border border-red-500/15 text-red-400 text-xs px-3 py-2.5 rounded"
              >
                {error}
              </motion.div>
            )}

            <p className="text-xs text-surface-700">
              Enter your email and we'll send you a link to reset your password.
            </p>

            <div>
              <label className="block text-[10px] font-semibold text-surface-600 mb-1.5 uppercase tracking-wider">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input-premium"
                placeholder="you@example.com"
              />
            </div>

            <motion.button
              type="submit"
              disabled={loading}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              className="btn-primary w-full !py-2.5"
            >
              {loading ? <Spinner className="w-4 h-4" /> : 'Send reset link'}
            </motion.button>
          </form>
        )}

        <p className="text-center text-xs text-surface-600 mt-6">
          Remember your password?{' '}
          <Link to="/login" className="text-brand-400 hover:text-brand-300 font-medium transition-colors duration-150">
            Log in
          </Link>
        </p>
      </motion.div>
    </div>
  );
}

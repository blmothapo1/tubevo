import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import Spinner from '../components/Spinner';

const ease = [0.25, 0.1, 0.25, 1];

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const me = await login(email, password);
      // Admin users go straight to the Admin HQ
      navigate(me?.role === 'admin' ? '/admin' : '/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-surface-50 flex items-center justify-center px-5 relative overflow-hidden">
      {/* Ambient background — subtle */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[500px] h-[350px] bg-brand-600/4 rounded-full blur-[100px] pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease }}
        className="w-full max-w-[380px] relative z-10"
      >
        <div className="text-center mb-8">
          <Link to="/">
            <span className="text-[22px] font-semibold text-white mx-auto block text-center" style={{ fontFamily: "'Poppins', sans-serif" }}>Tubevo</span>
          </Link>
          <p className="mt-2.5 text-xs text-surface-600 uppercase tracking-wider font-medium">Welcome back</p>
        </div>

        <form onSubmit={handleSubmit} className="card p-7 space-y-6">
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-red-500/6 text-red-400 text-[13px] px-3 py-2.5 rounded-[10px]"
            >
              {error}
            </motion.div>
          )}

          <div>
            <label className="block text-[11px] font-semibold text-surface-600 mb-2 uppercase tracking-[0.06em]">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input-premium"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-surface-600 mb-2 uppercase tracking-[0.06em]">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input-premium"
              placeholder="••••••••"
            />
            <div className="mt-2 text-right">
              <Link to="/forgot-password" className="text-[11px] text-brand-400 hover:text-brand-300 transition-colors duration-150">
                Forgot password?
              </Link>
            </div>
          </div>

          <motion.button
            type="submit"
            disabled={loading}
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
            className="btn-primary w-full"
          >
            {loading ? <Spinner className="w-4 h-4" /> : 'Log in'}
          </motion.button>
        </form>

        <p className="text-center text-[13px] text-surface-600 mt-7">
          Don't have an account?{' '}
          <Link to="/signup" className="text-brand-400 hover:text-brand-300 font-medium transition-colors duration-150">
            Sign up
          </Link>
        </p>
      </motion.div>
    </div>
  );
}

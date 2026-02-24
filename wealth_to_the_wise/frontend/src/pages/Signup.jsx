import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import Spinner from '../components/Spinner';
import tubevoLogo from '../assets/tubevo-logo-web.png';

const ease = [0.25, 0.1, 0.25, 1];

export default function Signup() {
  const { signup, login } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await signup(email, password, name);
      await login(email, password);
      navigate('/onboarding');
    } catch (err) {
      setError(err.response?.data?.detail || 'Signup failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-surface-50 flex items-center justify-center px-5 relative overflow-hidden">
      {/* Ambient background */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-brand-600/6 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-0 w-[300px] h-[300px] bg-accent-500/4 rounded-full blur-[80px] pointer-events-none" />

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
          <p className="mt-3 text-sm text-surface-600">Create your account</p>
        </div>

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

          <div>
            <label className="block text-xs font-medium text-surface-700 mb-2">Full name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input-premium"
              placeholder="Jane Doe"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-surface-700 mb-2">Email</label>
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
            <label className="block text-xs font-medium text-surface-700 mb-2">Password</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="input-premium"
              placeholder="Min 8 characters"
            />
          </div>

          <motion.button
            type="submit"
            disabled={loading}
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.98 }}
            className="btn-primary w-full !py-3"
          >
            {loading ? <Spinner className="w-4 h-4" /> : 'Create account'}
          </motion.button>
        </form>

        <p className="text-center text-sm text-surface-600 mt-7">
          Already have an account?{' '}
          <Link to="/login" className="text-brand-400 hover:text-brand-300 font-medium transition-colors duration-200">
            Log in
          </Link>
        </p>
      </motion.div>
    </div>
  );
}

import { useState, useEffect } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import Spinner from '../components/Spinner';

const ease = [0.25, 0.1, 0.25, 1];

export default function Signup() {
  const { signup, login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [referralCode] = useState(() => searchParams.get('ref') || '');
  const [referrerName, setReferrerName] = useState('');

  // Validate referral code on mount
  useEffect(() => {
    if (!referralCode) return;
    fetch(`${import.meta.env.VITE_API_URL || ''}/api/referrals/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: referralCode }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.valid && data.referrer_name) setReferrerName(data.referrer_name);
      })
      .catch(() => {});
  }, [referralCode]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await signup(email, password, name, referralCode || undefined);
      await login(email, password);
      navigate('/onboarding');
    } catch (err) {
      setError(err.response?.data?.detail || 'Signup failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-surface-50 flex items-center justify-center px-6 relative overflow-hidden">
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
          <p className="mt-2.5 text-xs text-surface-600 uppercase tracking-wider font-medium">Create your account</p>
        </div>

        <form onSubmit={handleSubmit} className="card p-7 space-y-6">
          {referrerName && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-brand-500/8 text-brand-400 text-[13px] px-3 py-2.5 rounded-[10px] flex items-center gap-2"
            >
              <span className="text-[14px]">🎁</span>
              Referred by <span className="font-semibold">{referrerName}</span>
            </motion.div>
          )}

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
            <label className="block text-[11px] font-semibold text-surface-600 mb-2 uppercase tracking-[0.06em]">Full name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input-premium"
              placeholder="Jane Doe"
            />
          </div>

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
            whileTap={{ scale: 0.99 }}
            className="btn-primary w-full"
          >
            {loading ? <Spinner className="w-4 h-4" /> : 'Create account'}
          </motion.button>
        </form>

        <p className="text-center text-[13px] text-surface-600 mt-7">
          Already have an account?{' '}
          <Link to="/login" className="text-brand-400 hover:text-brand-300 font-medium transition-colors duration-150">
            Log in
          </Link>
        </p>
      </motion.div>
    </div>
  );
}

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import Spinner from '../components/Spinner';

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
    <div className="min-h-screen bg-surface-50 flex items-center justify-center px-4 relative overflow-hidden">
      {/* Decorative glow blobs */}
      <div className="absolute top-1/3 -right-32 w-96 h-96 bg-brand-600/8 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/3 -left-32 w-80 h-80 bg-accent-500/6 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-sm relative z-10">
        <div className="text-center mb-8">
          <Link to="/" className="text-2xl font-bold tracking-tight text-white">
            <span className="text-gradient">Tube</span>vo
          </Link>
          <p className="mt-2 text-sm text-surface-700">Create your account</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-surface-100 border border-surface-300 rounded-xl p-6 space-y-4 glow-brand">
          {error && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-sm px-4 py-2.5 rounded-lg">
              {error}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-surface-700 mb-1.5">Full name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-surface-200 border border-surface-400 rounded-lg px-3 py-2.5 text-sm text-white placeholder-surface-600 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500 transition"
              placeholder="Jane Doe"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-surface-700 mb-1.5">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-surface-200 border border-surface-400 rounded-lg px-3 py-2.5 text-sm text-white placeholder-surface-600 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500 transition"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-surface-700 mb-1.5">Password</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-surface-200 border border-surface-400 rounded-lg px-3 py-2.5 text-sm text-white placeholder-surface-600 focus:outline-none focus:ring-2 focus:ring-brand-500/40 focus:border-brand-500 transition"
              placeholder="Min 8 characters"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full gradient-brand hover:opacity-90 disabled:opacity-50 text-white font-medium text-sm py-2.5 rounded-lg transition-all flex items-center justify-center gap-2 glow-brand"
          >
            {loading ? <Spinner className="w-4 h-4" /> : 'Create account'}
          </button>
        </form>

        <p className="text-center text-sm text-surface-600 mt-5">
          Already have an account?{' '}
          <Link to="/login" className="text-brand-400 hover:text-brand-300 transition-colors">
            Log in
          </Link>
        </p>
      </div>
    </div>
  );
}

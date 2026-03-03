import { useState, useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { motion } from 'framer-motion';
import { getAccessToken } from '../lib/api';

/**
 * AdminRoute — wraps routes that require role='admin'.
 *
 * 1. Checks client-side user.role first (fast reject).
 * 2. Verifies server-side via GET /api/admin/verify (authoritative).
 * 3. Non-admins are redirected to /dashboard.
 */
export default function AdminRoute({ children }) {
  const { user, loading: authLoading } = useAuth();
  const [verified, setVerified] = useState(null); // null = pending, true/false = result

  useEffect(() => {
    // Don't verify until auth has loaded and we have a user
    if (authLoading || !user) return;

    // Fast client-side reject
    if (user.role !== 'admin') {
      setVerified(false);
      return;
    }

    // Server-side verification — use raw fetch to avoid axios interceptor redirect loop
    let cancelled = false;
    const token = getAccessToken();
    fetch('/api/admin/verify', {
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    })
      .then((res) => {
        if (!cancelled) setVerified(res.ok);
      })
      .catch(() => { if (!cancelled) setVerified(false); });
    return () => { cancelled = true; };
  }, [user, authLoading]);

  // Still loading auth
  if (authLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-50">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-col items-center gap-4"
        >
          <motion.div
            animate={{ scale: [1, 1.08, 1], opacity: [0.6, 1, 0.6] }}
            transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
            className="w-10 h-10 rounded-[10px] bg-brand-500"
          />
          <div className="flex gap-1">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                animate={{ opacity: [0.3, 1, 0.3] }}
                transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.15, ease: 'easeInOut' }}
                className="w-1.5 h-1.5 rounded-full bg-brand-400"
              />
            ))}
          </div>
        </motion.div>
      </div>
    );
  }

  // Not logged in at all
  if (!user) return <Navigate to="/login" replace />;

  // Server verification pending
  if (verified === null) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-50">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-col items-center gap-4"
        >
          <motion.div
            animate={{ scale: [1, 1.08, 1], opacity: [0.6, 1, 0.6] }}
            transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
            className="w-10 h-10 rounded-[10px] bg-brand-500"
          />
          <p className="text-[13px] text-surface-600">Verifying access…</p>
        </motion.div>
      </div>
    );
  }

  // Verification failed — not admin
  if (!verified) return <Navigate to="/dashboard" replace />;

  return children;
}

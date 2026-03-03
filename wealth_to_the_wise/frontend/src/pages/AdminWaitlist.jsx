import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { getAccessToken, API_BASE } from '../lib/api';
import { FadeIn, StaggerContainer, StaggerItem } from '../components/Motion';
import {
  Shield,
  ArrowLeft,
  Mail,
  Search,
  RefreshCw,
  UserPlus,
  CheckCircle2,
  Clock,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  X,
} from 'lucide-react';

function timeSince(dateStr) {
  if (!dateStr) return '';
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

async function adminFetch(path, options = {}) {
  const token = getAccessToken();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export default function AdminWaitlist() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [inviting, setInviting] = useState(null);
  const [toast, setToast] = useState(null);

  const pageSize = 25;

  const fetchWaitlist = useCallback(async () => {
    try {
      setError(null);
      const params = new URLSearchParams({ page, page_size: pageSize });
      if (search.trim()) params.set('search', search.trim());
      const res = await adminFetch(`/api/admin/waitlist?${params}`);
      setData(res);
    } catch {
      setError('Failed to load waitlist.');
    } finally {
      setLoading(false);
    }
  }, [search, page]);

  useEffect(() => { fetchWaitlist(); }, [fetchWaitlist]);

  // Debounced search
  useEffect(() => {
    setPage(1);
  }, [search]);

  async function handleInviteBeta(email) {
    setInviting(email);
    try {
      const res = await adminFetch('/api/admin/waitlist/invite-beta', {
        method: 'POST',
        body: JSON.stringify({ email }),
      });
      setToast({ type: 'success', message: res.message });
      // Refresh to update any status
      setTimeout(() => setToast(null), 4000);
    } catch {
      setToast({ type: 'error', message: `Failed to invite ${email}` });
      setTimeout(() => setToast(null), 4000);
    } finally {
      setInviting(null);
    }
  }

  const totalPages = data ? Math.ceil(data.total / pageSize) : 1;

  return (
    <div className="min-h-screen bg-surface-50 flex flex-col">
      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <header className="h-[60px] glass sticky top-0 z-20 flex items-center justify-between px-5 sm:px-8 safe-area-inset">
        <div className="flex items-center gap-3">
          <motion.button
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.94 }}
            onClick={() => navigate('/admin')}
            className="p-2 -ml-2 rounded-[8px] text-surface-600 hover:text-surface-800 hover:bg-white/[0.04] transition-colors duration-150"
          >
            <ArrowLeft size={16} />
          </motion.button>
          <span className="text-[18px] sm:text-[20px] font-semibold text-white" style={{ fontFamily: "'Poppins', sans-serif" }}>
            Tubevo
          </span>
          <span className="text-[11px] font-medium tracking-wide uppercase px-2 py-0.5 rounded-[5px] bg-brand-500/15 text-brand-400">
            Admin
          </span>
        </div>

        <div className="flex items-center gap-3">
          <motion.button
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.94 }}
            onClick={() => { setLoading(true); fetchWaitlist(); }}
            className="p-2 rounded-[8px] text-surface-600 hover:text-surface-800 hover:bg-white/[0.04] transition-colors duration-150"
            title="Refresh"
          >
            <RefreshCw size={16} />
          </motion.button>
          <div className="flex items-center gap-2 text-[13px] text-surface-600">
            <Shield size={14} className="text-brand-400" />
            <span className="hidden sm:inline">{user?.email}</span>
          </div>
        </div>
      </header>

      {/* ── Content ─────────────────────────────────────────────────── */}
      <main className="flex-1 w-full max-w-5xl mx-auto px-5 py-6 sm:px-6 sm:py-8 lg:px-8">

        {/* Page title */}
        <FadeIn>
          <div className="mb-6">
            <h1 className="text-[22px] sm:text-[26px] font-semibold text-white tracking-tight flex items-center gap-3">
              <Mail size={24} className="text-violet-400" />
              Waitlist
            </h1>
            <p className="text-[12px] text-surface-600 mt-1.5 uppercase tracking-[0.08em] font-medium">
              {data ? `${data.total} signup${data.total !== 1 ? 's' : ''}` : 'Loading...'}
            </p>
          </div>
        </FadeIn>

        {/* Search bar */}
        <FadeIn delay={0.05}>
          <div className="relative mb-6">
            <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-surface-600" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by email or name..."
              className="input-premium pl-10 w-full max-w-md"
            />
          </div>
        </FadeIn>

        {/* Error */}
        {error && (
          <FadeIn>
            <div className="card px-5 py-4 mb-6 border-l-[3px] border-l-red-500">
              <p className="text-[13px] text-red-400">{error}</p>
            </div>
          </FadeIn>
        )}

        {/* Loading skeleton */}
        {loading && !data && (
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="card px-5 py-4 flex items-center gap-4">
                <div className="skeleton w-8 h-8 rounded-full" />
                <div className="flex-1 space-y-1.5">
                  <div className="skeleton h-3 w-48" />
                  <div className="skeleton h-2.5 w-24" />
                </div>
                <div className="skeleton h-7 w-24 rounded-[6px]" />
              </div>
            ))}
          </div>
        )}

        {/* ── Table ──────────────────────────────────────────────────── */}
        {data && (
          <FadeIn delay={0.1}>
            {data.items.length === 0 ? (
              <div className="card px-6 py-14 text-center">
                <Mail size={32} className="mx-auto text-surface-600 mb-3" />
                <p className="text-[14px] text-surface-700">
                  {search ? 'No waitlist entries match your search.' : 'No waitlist signups yet.'}
                </p>
              </div>
            ) : (
              <>
                <div className="card overflow-hidden">
                  {/* Header row */}
                  <div className="grid grid-cols-[1fr_140px_100px_100px] sm:grid-cols-[1fr_180px_120px_120px] px-4 py-2.5 border-b border-white/[0.04] text-[10px] font-semibold text-surface-600 uppercase tracking-[0.08em]">
                    <span>Email</span>
                    <span>Name</span>
                    <span>Joined</span>
                    <span className="text-right">Action</span>
                  </div>

                  {/* Rows */}
                  <StaggerContainer className="divide-y divide-white/[0.03]">
                    {data.items.map((item) => (
                      <StaggerItem key={item.id}>
                        <div className="grid grid-cols-[1fr_140px_100px_100px] sm:grid-cols-[1fr_180px_120px_120px] px-4 py-3 items-center hover:bg-white/[0.015] transition-colors duration-100">
                          {/* Email */}
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-7 h-7 rounded-full bg-violet-500/15 flex items-center justify-center shrink-0">
                              <Mail size={12} className="text-violet-400" />
                            </div>
                            <span className="text-[13px] text-surface-800 truncate">{item.email}</span>
                          </div>

                          {/* Name */}
                          <span className="text-[13px] text-surface-600 truncate">
                            {item.name || '—'}
                          </span>

                          {/* Joined */}
                          <span className="text-[12px] text-surface-600 tabular-nums">
                            {timeSince(item.created_at)}
                          </span>

                          {/* Action */}
                          <div className="flex justify-end">
                            <motion.button
                              whileHover={{ scale: 1.04 }}
                              whileTap={{ scale: 0.96 }}
                              onClick={() => handleInviteBeta(item.email)}
                              disabled={inviting === item.email}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[6px] bg-emerald-500/10 text-emerald-400 text-[11px] font-medium hover:bg-emerald-500/20 transition-colors duration-150 disabled:opacity-50"
                            >
                              {inviting === item.email ? (
                                <RefreshCw size={11} className="animate-spin" />
                              ) : (
                                <Sparkles size={11} />
                              )}
                              Invite Beta
                            </motion.button>
                          </div>
                        </div>
                      </StaggerItem>
                    ))}
                  </StaggerContainer>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between mt-4 px-1">
                    <p className="text-[12px] text-surface-600 tabular-nums">
                      Page {page} of {totalPages} · {data.total} total
                    </p>
                    <div className="flex gap-1.5">
                      <motion.button
                        whileHover={{ scale: 1.06 }}
                        whileTap={{ scale: 0.94 }}
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page <= 1}
                        className="p-2 rounded-[8px] text-surface-600 hover:text-white hover:bg-white/[0.04] disabled:opacity-30 transition"
                      >
                        <ChevronLeft size={14} />
                      </motion.button>
                      <motion.button
                        whileHover={{ scale: 1.06 }}
                        whileTap={{ scale: 0.94 }}
                        onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                        disabled={page >= totalPages}
                        className="p-2 rounded-[8px] text-surface-600 hover:text-white hover:bg-white/[0.04] disabled:opacity-30 transition"
                      >
                        <ChevronRight size={14} />
                      </motion.button>
                    </div>
                  </div>
                )}
              </>
            )}
          </FadeIn>
        )}
      </main>

      {/* ── Toast notification ──────────────────────────────────────── */}
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-[10px] shadow-lg ${
              toast.type === 'success' ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/15 text-red-400 border border-red-500/20'
            }`}
          >
            {toast.type === 'success' ? <CheckCircle2 size={16} /> : <X size={16} />}
            <span className="text-[13px] font-medium">{toast.message}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

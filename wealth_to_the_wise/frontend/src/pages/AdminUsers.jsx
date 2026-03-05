import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from '../contexts/AuthContext';
import api from '../lib/api';
import { FadeIn } from '../components/Motion';
import {
  Shield,
  Search,
  ChevronLeft,
  ChevronRight,
  Users,
  X,
  Film,
  ShieldCheck,
  ShieldOff,
  Coins,
  Ban,
  CheckCircle2,
  ArrowLeft,
  RefreshCw,
  AlertTriangle,
  ExternalLink,
} from 'lucide-react';

// ── Helpers ─────────────────────────────────────────────────────────

function fmtDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function fmtDateTime(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function timeSince(dateStr) {
  if (!dateStr) return '—';
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

const STATUS_COLORS = {
  posted: 'text-emerald-400 bg-emerald-500/10',
  completed: 'text-emerald-400 bg-emerald-500/10',
  generating: 'text-brand-400 bg-brand-500/10',
  pending: 'text-amber-400 bg-amber-500/10',
  failed: 'text-red-400 bg-red-500/10',
};


// ══════════════════════════════════════════════════════════════════════
// Main page
// ══════════════════════════════════════════════════════════════════════

export default function AdminUsers() {
  const { user: me } = useAuth();
  const navigate = useNavigate();

  // ── List state ──────────────────────────────────────────────────
  const [users, setUsers] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [totalPages, setTotalPages] = useState(1);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [loading, setLoading] = useState(true);

  // ── Detail state ────────────────────────────────────────────────
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // ── Action state ────────────────────────────────────────────────
  const [actionLoading, setActionLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState(null);
  const [creditAmount, setCreditAmount] = useState('');
  const [creditReason, setCreditReason] = useState('');

  // ── Fetch user list ─────────────────────────────────────────────
  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('page', page);
      params.set('page_size', pageSize);
      if (search) params.set('search', search);
      if (roleFilter) params.set('role', roleFilter);

      const { data } = await api.get(`/api/admin/users?${params}`);
      setUsers(data.users);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch {
      // degrade gracefully
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, roleFilter]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  // Reset to page 1 when filters change
  useEffect(() => { setPage(1); }, [search, roleFilter]);

  // ── Fetch user detail ───────────────────────────────────────────
  const openDetail = async (userId) => {
    setDetailLoading(true);
    setDetail(null);
    setActionMsg(null);
    try {
      const { data } = await api.get(`/api/admin/users/${userId}`);
      setDetail(data);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => { setDetail(null); setActionMsg(null); setCreditAmount(''); setCreditReason(''); };

  // ── Actions ─────────────────────────────────────────────────────
  const doAction = async (fn) => {
    setActionLoading(true);
    setActionMsg(null);
    try {
      const msg = await fn();
      setActionMsg({ type: 'success', text: msg });
      // Refresh detail & list
      if (detail) await openDetail(detail.id);
      fetchUsers();
    } catch (err) {
      setActionMsg({ type: 'error', text: err.response?.data?.detail || 'Action failed.' });
    } finally {
      setActionLoading(false);
    }
  };

  const changeRole = (userId, newRole) => doAction(async () => {
    const { data } = await api.patch(`/api/admin/users/${userId}/role`, { role: newRole });
    return data.message;
  });

  const grantCredits = (userId) => doAction(async () => {
    const amt = parseInt(creditAmount, 10);
    if (!amt || amt < 1) throw new Error('Enter a valid amount.');
    const { data } = await api.post(`/api/admin/users/${userId}/credits`, { amount: amt, reason: creditReason });
    setCreditAmount('');
    setCreditReason('');
    return data.message;
  });

  const toggleDisable = (userId, disable) => doAction(async () => {
    const { data } = await api.patch(`/api/admin/users/${userId}/disable`, { disabled: disable });
    return data.message;
  });

  // ══════════════════════════════════════════════════════════════════
  // Render
  // ══════════════════════════════════════════════════════════════════

  return (
    <div className="min-h-screen bg-surface-50 flex flex-col">
      {/* ── Top bar ───────────────────────────────────────────────── */}
      <header className="h-[60px] glass sticky top-0 z-20 flex items-center justify-between mobile-content-padding sm:px-8 safe-area-inset">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/admin')}
            className="p-1.5 -ml-1.5 rounded-[6px] text-surface-600 hover:text-white hover:bg-white/[0.04] transition-colors duration-150"
          >
            <ArrowLeft size={18} />
          </button>
          <span className="text-[18px] sm:text-[20px] font-semibold text-white" style={{ fontFamily: "'Poppins', sans-serif" }}>
            Tubevo
          </span>
          <span className="text-[11px] font-medium tracking-wide uppercase px-2 py-0.5 rounded-[5px] bg-brand-500/15 text-brand-400">
            Admin
          </span>
        </div>
        <div className="flex items-center gap-2 text-[13px] text-surface-600">
          <Shield size={14} className="text-brand-400" />
          <span className="hidden sm:inline">{me?.email}</span>
        </div>
      </header>

      <main className="flex-1 w-full max-w-6xl mx-auto mobile-content-padding sm:px-8 sm:py-8 lg:px-10">

        {/* ── Page title ─────────────────────────────────────────── */}
        <FadeIn>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-[22px] sm:text-[26px] font-semibold text-white tracking-tight flex items-center gap-2">
                <Users size={22} className="text-brand-400" /> Users
              </h1>
              <p className="text-[12px] text-surface-600 mt-1 uppercase tracking-[0.08em] font-medium">
                {total} total users
              </p>
            </div>
            <motion.button
              whileHover={{ scale: 1.06 }}
              whileTap={{ scale: 0.94 }}
              onClick={fetchUsers}
              className="p-2 rounded-[8px] text-surface-600 hover:text-surface-800 hover:bg-white/[0.04] transition-colors"
            >
              <RefreshCw size={16} />
            </motion.button>
          </div>
        </FadeIn>

        {/* ── Filters ────────────────────────────────────────────── */}
        <FadeIn delay={0.05}>
          <div className="flex flex-col sm:flex-row gap-3 mb-6">
            {/* Search */}
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-600" />
              <input
                type="text"
                placeholder="Search by email or name…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-9 pr-4 h-[38px] rounded-[8px] bg-surface-200 text-[13px] text-white placeholder:text-surface-600 focus:outline-none focus:ring-1 focus:ring-brand-500/40 transition-all"
              />
              {search && (
                <button onClick={() => setSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-surface-600 hover:text-surface-800">
                  <X size={13} />
                </button>
              )}
            </div>

            {/* Role filter */}
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="h-[38px] px-3 rounded-[8px] bg-surface-200 text-[13px] text-white focus:outline-none focus:ring-1 focus:ring-brand-500/40 appearance-none cursor-pointer"
            >
              <option value="">All roles</option>
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
          </div>
        </FadeIn>

        {/* ── Table ──────────────────────────────────────────────── */}
        <FadeIn delay={0.1}>
          <div className="card overflow-hidden">
            {/* Header */}
            <div className="hidden sm:grid grid-cols-[1fr_100px_80px_100px_100px_100px] gap-3 px-4 py-2.5 text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] border-b border-white/[0.04]">
              <span>Email</span>
              <span>Role</span>
              <span>Plan</span>
              <span>Credits</span>
              <span>Last Login</span>
              <span>Last Video</span>
            </div>

            {loading ? (
              <div className="p-4 space-y-3">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="flex gap-3 items-center">
                    <div className="skeleton h-4 flex-1" />
                    <div className="skeleton h-4 w-16" />
                    <div className="skeleton h-4 w-12" />
                  </div>
                ))}
              </div>
            ) : users.length === 0 ? (
              <div className="px-6 py-14 text-center">
                <p className="text-[14px] text-surface-700">No users found.</p>
              </div>
            ) : (
              <div className="divide-y divide-white/[0.03]">
                {users.map((u) => (
                  <motion.div
                    key={u.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    onClick={() => openDetail(u.id)}
                    className="grid grid-cols-1 sm:grid-cols-[1fr_100px_80px_100px_100px_100px] gap-1 sm:gap-3 px-4 py-3 cursor-pointer hover:bg-white/[0.02] transition-colors duration-100"
                  >
                    {/* Email + name */}
                    <div className="min-w-0">
                      <p className="text-[13px] text-white truncate">{u.email}</p>
                      {u.full_name && <p className="text-[11px] text-surface-600 truncate">{u.full_name}</p>}
                      {!u.is_active && <span className="text-[10px] text-red-400 font-medium uppercase">Disabled</span>}
                    </div>
                    {/* Role */}
                    <span className={`text-[12px] font-medium ${u.role === 'admin' ? 'text-brand-400' : 'text-surface-700'} self-center`}>
                      {u.role}
                    </span>
                    {/* Plan */}
                    <span className="text-[12px] text-surface-700 self-center capitalize">{u.plan}</span>
                    {/* Credits remaining */}
                    <span className="text-[12px] text-surface-700 self-center tabular-nums">{u.credits_remaining}</span>
                    {/* Last login */}
                    <span className="text-[11px] text-surface-600 self-center tabular-nums">{timeSince(u.last_login_at)}</span>
                    {/* Last video */}
                    <span className="text-[11px] text-surface-600 self-center tabular-nums">{timeSince(u.last_video_created_at)}</span>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </FadeIn>

        {/* ── Pagination ─────────────────────────────────────────── */}
        {totalPages > 1 && (
          <FadeIn delay={0.15}>
            <div className="flex items-center justify-between mt-4">
              <p className="text-[12px] text-surface-600">
                Page {page} of {totalPages} · {total} users
              </p>
              <div className="flex gap-1.5">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="p-1.5 rounded-[6px] text-surface-600 hover:text-white hover:bg-white/[0.04] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronLeft size={16} />
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="p-1.5 rounded-[6px] text-surface-600 hover:text-white hover:bg-white/[0.04] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </FadeIn>
        )}
      </main>

      {/* ══════════════════════════════════════════════════════════════
         Detail drawer (slide-over)
         ══════════════════════════════════════════════════════════════ */}
      <AnimatePresence>
        {(detail || detailLoading) && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/50 backdrop-blur-sm z-30"
              onClick={closeDetail}
            />
            {/* Panel */}
            <motion.aside
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'tween', duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
              className="fixed right-0 top-0 bottom-0 w-full sm:w-[480px] max-w-full bg-surface-100 z-40 flex flex-col overflow-y-auto"
            >
              {/* Header */}
              <div className="sticky top-0 z-10 glass px-5 py-4 flex items-center justify-between">
                <h2 className="text-[16px] font-semibold text-white">User Detail</h2>
                <button onClick={closeDetail} className="p-1.5 rounded-[6px] text-surface-600 hover:text-white hover:bg-white/[0.04]">
                  <X size={16} />
                </button>
              </div>

              {detailLoading && !detail && (
                <div className="p-5 space-y-4">
                  {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-5 w-full" />)}
                </div>
              )}

              {detail && (
                <div className="p-5 space-y-6">

                  {/* ── Action messages ──────────────────────────── */}
                  {actionMsg && (
                    <div className={`px-4 py-2.5 rounded-[8px] text-[13px] font-medium ${actionMsg.type === 'success' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
                      {actionMsg.text}
                    </div>
                  )}

                  {/* ── Profile ──────────────────────────────────── */}
                  <section>
                    <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3">Profile</h3>
                    <div className="card p-4 space-y-2.5">
                      <Row label="ID" value={detail.id} mono />
                      <Row label="Email" value={detail.email} />
                      <Row label="Name" value={detail.full_name || '—'} />
                      <Row label="Role" value={detail.role} badge={detail.role === 'admin' ? 'brand' : 'surface'} />
                      <Row label="Active" value={detail.is_active ? 'Yes' : 'Disabled'} badge={detail.is_active ? 'green' : 'red'} />
                      <Row label="Verified" value={detail.is_verified ? 'Yes' : 'No'} />
                      <Row label="Beta" value={detail.is_beta ? 'Yes' : 'No'} />
                      <Row label="Joined" value={fmtDate(detail.created_at)} />
                      <Row label="Last Login" value={fmtDateTime(detail.last_login_at)} />
                    </div>
                  </section>

                  {/* ── Subscription ─────────────────────────────── */}
                  <section>
                    <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3">Subscription</h3>
                    <div className="card p-4 space-y-2.5">
                      <Row label="Plan" value={detail.plan} />
                      <Row label="Credits" value={detail.credit_balance} />
                      <Row label="Credits remaining" value={detail.credits_remaining} />
                      <Row label="Stripe ID" value={detail.stripe_customer_id || '—'} mono />
                    </div>
                  </section>

                  {/* ── Admin Actions ────────────────────────────── */}
                  <section>
                    <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3">Actions</h3>
                    <div className="space-y-3">
                      {/* Change role */}
                      <div className="card p-4">
                        <p className="text-[12px] text-surface-700 mb-2">Change role</p>
                        <div className="flex gap-2">
                          <ActionBtn
                            icon={ShieldCheck}
                            label="Make admin"
                            disabled={detail.role === 'admin' || actionLoading}
                            onClick={() => changeRole(detail.id, 'admin')}
                            color="brand"
                          />
                          <ActionBtn
                            icon={ShieldOff}
                            label="Make user"
                            disabled={detail.role === 'user' || actionLoading}
                            onClick={() => changeRole(detail.id, 'user')}
                            color="surface"
                          />
                        </div>
                      </div>

                      {/* Grant credits */}
                      <div className="card p-4">
                        <p className="text-[12px] text-surface-700 mb-2">Grant credits</p>
                        <div className="flex gap-2 mb-2">
                          <input
                            type="number"
                            placeholder="Amount"
                            min={1}
                            value={creditAmount}
                            onChange={(e) => setCreditAmount(e.target.value)}
                            className="w-24 h-[34px] px-3 rounded-[6px] bg-surface-200 text-[13px] text-white placeholder:text-surface-600 focus:outline-none focus:ring-1 focus:ring-brand-500/40"
                          />
                          <input
                            type="text"
                            placeholder="Reason (optional)"
                            value={creditReason}
                            onChange={(e) => setCreditReason(e.target.value)}
                            className="flex-1 h-[34px] px-3 rounded-[6px] bg-surface-200 text-[13px] text-white placeholder:text-surface-600 focus:outline-none focus:ring-1 focus:ring-brand-500/40"
                          />
                        </div>
                        <ActionBtn
                          icon={Coins}
                          label="Grant"
                          disabled={!creditAmount || actionLoading}
                          onClick={() => grantCredits(detail.id)}
                          color="amber"
                        />
                      </div>

                      {/* Disable / Enable */}
                      <div className="card p-4">
                        <p className="text-[12px] text-surface-700 mb-2">Account status</p>
                        {detail.is_active ? (
                          <ActionBtn
                            icon={Ban}
                            label="Disable user"
                            disabled={actionLoading}
                            onClick={() => toggleDisable(detail.id, true)}
                            color="red"
                          />
                        ) : (
                          <ActionBtn
                            icon={CheckCircle2}
                            label="Re-enable user"
                            disabled={actionLoading}
                            onClick={() => toggleDisable(detail.id, false)}
                            color="green"
                          />
                        )}
                      </div>
                    </div>
                  </section>

                  {/* ── Recent Videos ────────────────────────────── */}
                  <section>
                    <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3">
                      Recent Videos ({detail.recent_videos?.length || 0})
                    </h3>
                    {(detail.recent_videos?.length || 0) === 0 ? (
                      <div className="card px-4 py-8 text-center">
                        <p className="text-[13px] text-surface-600">No videos yet.</p>
                      </div>
                    ) : (
                      <div className="card overflow-hidden divide-y divide-white/[0.03]">
                        {detail.recent_videos.map((v) => (
                          <div key={v.id} className="px-4 py-3 flex items-center gap-3">
                            <div className="flex-1 min-w-0">
                              <p className="text-[13px] text-white truncate">{v.title}</p>
                              <p className="text-[11px] text-surface-600 truncate">{v.topic}</p>
                            </div>
                            <span className={`text-[11px] font-medium px-2 py-0.5 rounded-[5px] ${STATUS_COLORS[v.status] || 'text-surface-600 bg-surface-200'}`}>
                              {v.status}
                            </span>
                            {v.youtube_url && (
                              <a href={v.youtube_url} target="_blank" rel="noopener noreferrer" className="text-surface-600 hover:text-brand-400">
                                <ExternalLink size={13} />
                              </a>
                            )}
                            <span className="text-[10px] text-surface-600 tabular-nums shrink-0">{timeSince(v.created_at)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </section>

                  {/* ── Audit Log ────────────────────────────────── */}
                  {(detail.audit_log?.length || 0) > 0 && (
                    <section>
                      <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3">
                        Audit Log ({detail.audit_log.length})
                      </h3>
                      <div className="card overflow-hidden divide-y divide-white/[0.03]">
                        {detail.audit_log.map((entry) => (
                          <div key={entry.id} className="px-4 py-2.5">
                            <div className="flex items-center justify-between">
                              <span className="text-[12px] font-medium text-surface-800">{entry.action.replace(/_/g, ' ')}</span>
                              <span className="text-[10px] text-surface-600 tabular-nums">{timeSince(entry.created_at)}</span>
                            </div>
                            <p className="text-[11px] text-surface-600 mt-0.5">
                              by {entry.admin_email || entry.admin_id}
                              {entry.details && ` · ${JSON.stringify(entry.details)}`}
                            </p>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                </div>
              )}
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}


// ══════════════════════════════════════════════════════════════════════
// Subcomponents
// ══════════════════════════════════════════════════════════════════════

function Row({ label, value, mono = false, badge = null }) {
  const badgeColors = {
    brand: 'text-brand-400 bg-brand-500/10',
    surface: 'text-surface-700 bg-surface-300',
    green: 'text-emerald-400 bg-emerald-500/10',
    red: 'text-red-400 bg-red-500/10',
  };

  return (
    <div className="flex items-center justify-between">
      <span className="text-[12px] text-surface-600">{label}</span>
      {badge ? (
        <span className={`text-[11px] font-medium px-2 py-0.5 rounded-[5px] ${badgeColors[badge] || ''}`}>{String(value)}</span>
      ) : (
        <span className={`text-[13px] text-white ${mono ? 'font-mono text-[11px] text-surface-700' : ''}`}>{String(value)}</span>
      )}
    </div>
  );
}

function ActionBtn({ icon: Icon, label, onClick, disabled = false, color = 'brand' }) {
  const colors = {
    brand: 'bg-brand-500/10 text-brand-400 hover:bg-brand-500/20',
    surface: 'bg-surface-300 text-surface-700 hover:bg-surface-400',
    amber: 'bg-amber-500/10 text-amber-400 hover:bg-amber-500/20',
    red: 'bg-red-500/10 text-red-400 hover:bg-red-500/20',
    green: 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20',
  };

  return (
    <motion.button
      whileHover={{ scale: disabled ? 1 : 1.01 }}
      whileTap={{ scale: disabled ? 1 : 0.97 }}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 px-3 h-[32px] rounded-[6px] text-[12px] font-medium transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed ${colors[color] || colors.brand}`}
    >
      <Icon size={13} />
      {label}
    </motion.button>
  );
}

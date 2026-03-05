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
  AlertTriangle,
  X,
  ArrowLeft,
  RefreshCw,
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronUp,
  Link2,
  Film,
  User,
  Bug,
  Upload,
  Lock,
  Server,
  Zap,
} from 'lucide-react';

// ── Helpers ─────────────────────────────────────────────────────────

function timeSince(dateStr) {
  if (!dateStr) return '—';
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function fmtDateTime(d) {
  if (!d) return '—';
  return new Date(d).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

const TYPE_CONFIG = {
  pipeline:  { icon: Zap,           color: 'text-amber-400',   bg: 'bg-amber-500/10',   label: 'Pipeline' },
  upload:    { icon: Upload,         color: 'text-cyan-400',    bg: 'bg-cyan-500/10',    label: 'Upload' },
  auth:      { icon: Lock,           color: 'text-violet-400',  bg: 'bg-violet-500/10',  label: 'Auth' },
  api:       { icon: Bug,            color: 'text-brand-400',   bg: 'bg-brand-500/10',   label: 'API' },
  system:    { icon: Server,         color: 'text-red-400',     bg: 'bg-red-500/10',     label: 'System' },
};

function getTypeCfg(t) {
  return TYPE_CONFIG[t] || { icon: AlertTriangle, color: 'text-surface-600', bg: 'bg-surface-200', label: t };
}


// ══════════════════════════════════════════════════════════════════════
// Main page
// ══════════════════════════════════════════════════════════════════════

export default function AdminErrors() {
  const { user: me } = useAuth();
  const navigate = useNavigate();

  // ── List state ──────────────────────────────────────────────────
  const [errors, setErrors] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [totalPages, setTotalPages] = useState(1);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [resolvedFilter, setResolvedFilter] = useState('false');
  const [loading, setLoading] = useState(true);

  // ── Detail state ────────────────────────────────────────────────
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // ── Action state ────────────────────────────────────────────────
  const [actionLoading, setActionLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState(null);
  const [linkVideoId, setLinkVideoId] = useState('');

  // ── Fetch list ──────────────────────────────────────────────────
  const fetchErrors = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('page', page);
      params.set('page_size', pageSize);
      if (search) params.set('search', search);
      if (typeFilter) params.set('type', typeFilter);
      if (resolvedFilter) params.set('resolved', resolvedFilter);

      const { data } = await api.get(`/api/admin/errors?${params}`);
      setErrors(data.errors);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch {
      // degrade
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, typeFilter, resolvedFilter]);

  useEffect(() => { fetchErrors(); }, [fetchErrors]);
  useEffect(() => { setPage(1); }, [search, typeFilter, resolvedFilter]);

  // ── Fetch detail ────────────────────────────────────────────────
  const openDetail = async (errorId) => {
    setDetailLoading(true);
    setDetail(null);
    setActionMsg(null);
    setLinkVideoId('');
    try {
      const { data } = await api.get(`/api/admin/errors/${errorId}`);
      setDetail(data);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => { setDetail(null); setActionMsg(null); setLinkVideoId(''); };

  // ── Actions ─────────────────────────────────────────────────────
  const doAction = async (fn) => {
    setActionLoading(true);
    setActionMsg(null);
    try {
      const msg = await fn();
      setActionMsg({ type: 'success', text: msg });
      if (detail) await openDetail(detail.id);
      fetchErrors();
    } catch (err) {
      setActionMsg({ type: 'error', text: err.response?.data?.detail || 'Action failed.' });
    } finally {
      setActionLoading(false);
    }
  };

  const toggleResolve = (errorId, resolved) => doAction(async () => {
    const { data } = await api.patch(`/api/admin/errors/${errorId}/resolve`, { resolved });
    return data.message;
  });

  const linkVideo = (errorId) => doAction(async () => {
    if (!linkVideoId.trim()) throw new Error('Enter a video ID.');
    const { data } = await api.patch(`/api/admin/errors/${errorId}/link`, { video_id: linkVideoId.trim() });
    setLinkVideoId('');
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
                <AlertTriangle size={22} className="text-red-400" /> Errors
              </h1>
              <p className="text-[12px] text-surface-600 mt-1 uppercase tracking-[0.08em] font-medium">
                {total} total errors
              </p>
            </div>
            <motion.button
              whileHover={{ scale: 1.06 }}
              whileTap={{ scale: 0.94 }}
              onClick={fetchErrors}
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
                placeholder="Search by message or user email…"
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

            {/* Type */}
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="h-[38px] px-3 rounded-[8px] bg-surface-200 text-[13px] text-white focus:outline-none focus:ring-1 focus:ring-brand-500/40 appearance-none cursor-pointer"
            >
              <option value="">All types</option>
              <option value="pipeline">Pipeline</option>
              <option value="upload">Upload</option>
              <option value="auth">Auth</option>
              <option value="api">API</option>
              <option value="system">System</option>
            </select>

            {/* Resolved */}
            <select
              value={resolvedFilter}
              onChange={(e) => setResolvedFilter(e.target.value)}
              className="h-[38px] px-3 rounded-[8px] bg-surface-200 text-[13px] text-white focus:outline-none focus:ring-1 focus:ring-brand-500/40 appearance-none cursor-pointer"
            >
              <option value="">All</option>
              <option value="false">Unresolved</option>
              <option value="true">Resolved</option>
            </select>
          </div>
        </FadeIn>

        {/* ── Table ──────────────────────────────────────────────── */}
        <FadeIn delay={0.1}>
          <div className="card overflow-hidden">
            {/* Header */}
            <div className="hidden sm:grid grid-cols-[80px_1fr_120px_80px_100px_80px] gap-3 px-4 py-2.5 text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] border-b border-white/[0.04]">
              <span>Type</span>
              <span>Message</span>
              <span>User</span>
              <span>Video</span>
              <span>Time</span>
              <span>Status</span>
            </div>

            {loading ? (
              <div className="p-4 space-y-3">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="flex gap-3 items-center">
                    <div className="skeleton h-4 w-16" />
                    <div className="skeleton h-4 flex-1" />
                    <div className="skeleton h-4 w-20" />
                  </div>
                ))}
              </div>
            ) : errors.length === 0 ? (
              <div className="px-6 py-14 text-center">
                <CheckCircle2 size={28} className="mx-auto text-emerald-400/60 mb-3" />
                <p className="text-[14px] text-surface-700">No errors found.</p>
                <p className="text-[12px] text-surface-600 mt-1">All clear!</p>
              </div>
            ) : (
              <div className="divide-y divide-white/[0.03]">
                {errors.map((e) => {
                  const cfg = getTypeCfg(e.type);
                  const Icon = cfg.icon;
                  return (
                    <motion.div
                      key={e.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      onClick={() => openDetail(e.id)}
                      className="grid grid-cols-1 sm:grid-cols-[80px_1fr_120px_80px_100px_80px] gap-1 sm:gap-3 px-4 py-3 cursor-pointer hover:bg-white/[0.02] transition-colors duration-100"
                    >
                      {/* Type badge */}
                      <div className="flex items-center gap-1.5 self-center">
                        <div className={`w-6 h-6 rounded-[5px] ${cfg.bg} flex items-center justify-center shrink-0`}>
                          <Icon size={12} className={cfg.color} />
                        </div>
                        <span className={`text-[11px] font-medium ${cfg.color} hidden sm:inline`}>{cfg.label}</span>
                      </div>

                      {/* Message */}
                      <div className="min-w-0 self-center">
                        <p className={`text-[13px] truncate ${e.resolved ? 'text-surface-600 line-through' : 'text-white'}`}>
                          {e.message}
                        </p>
                      </div>

                      {/* User */}
                      <span className="text-[11px] text-surface-600 self-center truncate">
                        {e.user_email || '—'}
                      </span>

                      {/* Video */}
                      <span className="text-[11px] text-surface-600 self-center font-mono truncate">
                        {e.video_id ? e.video_id.slice(0, 8) : '—'}
                      </span>

                      {/* Time */}
                      <span className="text-[11px] text-surface-600 self-center tabular-nums">{timeSince(e.created_at)}</span>

                      {/* Status */}
                      {e.resolved ? (
                        <span className="text-[11px] font-medium text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-[5px] self-center text-center">
                          Resolved
                        </span>
                      ) : (
                        <span className="text-[11px] font-medium text-red-400 bg-red-500/10 px-2 py-0.5 rounded-[5px] self-center text-center">
                          Open
                        </span>
                      )}
                    </motion.div>
                  );
                })}
              </div>
            )}
          </div>
        </FadeIn>

        {/* ── Pagination ─────────────────────────────────────────── */}
        {totalPages > 1 && (
          <FadeIn delay={0.15}>
            <div className="flex items-center justify-between mt-4">
              <p className="text-[12px] text-surface-600">
                Page {page} of {totalPages} · {total} errors
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
         Detail drawer
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
              className="fixed right-0 top-0 bottom-0 w-full sm:w-[500px] max-w-full bg-surface-100 z-40 flex flex-col overflow-y-auto"
            >
              {/* Header */}
              <div className="sticky top-0 z-10 glass px-5 py-4 flex items-center justify-between">
                <h2 className="text-[16px] font-semibold text-white">Error Detail</h2>
                <button onClick={closeDetail} className="p-1.5 rounded-[6px] text-surface-600 hover:text-white hover:bg-white/[0.04]">
                  <X size={16} />
                </button>
              </div>

              {detailLoading && !detail && (
                <div className="p-5 space-y-4">
                  {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-5 w-full" />)}
                </div>
              )}

              {detail && (
                <DetailPanel
                  detail={detail}
                  actionLoading={actionLoading}
                  actionMsg={actionMsg}
                  linkVideoId={linkVideoId}
                  setLinkVideoId={setLinkVideoId}
                  toggleResolve={toggleResolve}
                  linkVideo={linkVideo}
                  navigate={navigate}
                />
              )}
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}


// ══════════════════════════════════════════════════════════════════════
// Detail panel content
// ══════════════════════════════════════════════════════════════════════

function DetailPanel({ detail, actionLoading, actionMsg, linkVideoId, setLinkVideoId, toggleResolve, linkVideo, navigate }) {
  const [stackOpen, setStackOpen] = useState(false);
  const cfg = getTypeCfg(detail.type);
  const Icon = cfg.icon;

  return (
    <div className="p-5 space-y-6">

      {/* ── Action messages ────────────────────────────────────── */}
      {actionMsg && (
        <div className={`px-4 py-2.5 rounded-[8px] text-[13px] font-medium ${actionMsg.type === 'success' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
          {actionMsg.text}
        </div>
      )}

      {/* ── Overview ──────────────────────────────────────────── */}
      <section>
        <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3">Overview</h3>
        <div className="card p-4 space-y-2.5">
          <Row label="ID" value={detail.id} mono />
          <Row label="Type">
            <span className={`inline-flex items-center gap-1 text-[12px] font-medium px-2 py-0.5 rounded-[5px] ${cfg.bg} ${cfg.color}`}>
              <Icon size={11} /> {cfg.label}
            </span>
          </Row>
          <Row label="Status">
            {detail.resolved ? (
              <span className="text-[12px] font-medium text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-[5px]">
                Resolved
              </span>
            ) : (
              <span className="text-[12px] font-medium text-red-400 bg-red-500/10 px-2 py-0.5 rounded-[5px]">
                Open
              </span>
            )}
          </Row>
          <Row label="Time" value={fmtDateTime(detail.created_at)} />
          {detail.resolved_at && (
            <Row label="Resolved at" value={fmtDateTime(detail.resolved_at)} />
          )}
          {detail.resolved_by_email && (
            <Row label="Resolved by" value={detail.resolved_by_email} />
          )}
        </div>
      </section>

      {/* ── User / Video links ───────────────────────────────── */}
      <section>
        <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3">Context</h3>
        <div className="card p-4 space-y-2.5">
          <Row label="User">
            {detail.user_email ? (
              <button
                onClick={() => navigate('/admin/users')}
                className="text-[13px] text-brand-400 hover:underline"
              >
                {detail.user_email}
              </button>
            ) : (
              <span className="text-[13px] text-surface-600">—</span>
            )}
          </Row>
          <Row label="Video">
            {detail.video_id ? (
              <button
                onClick={() => navigate('/admin/videos')}
                className="text-[12px] font-mono text-brand-400 hover:underline"
              >
                {detail.video_id.slice(0, 12)}…
              </button>
            ) : (
              <span className="text-[13px] text-surface-600">Not linked</span>
            )}
          </Row>
        </div>
      </section>

      {/* ── Message ──────────────────────────────────────────── */}
      <section>
        <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3">Message</h3>
        <div className="card p-4">
          <p className="text-[13px] text-white whitespace-pre-wrap break-words leading-relaxed">{detail.message}</p>
        </div>
      </section>

      {/* ── Stack trace (collapsible) ─────────────────────────── */}
      {detail.stack && (
        <section>
          <button
            onClick={() => setStackOpen((o) => !o)}
            className="flex items-center gap-1.5 text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3 hover:text-surface-800 transition-colors"
          >
            Stack Trace
            {stackOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
          <AnimatePresence>
            {stackOpen && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="overflow-hidden"
              >
                <div className="card p-4 max-h-[400px] overflow-auto">
                  <pre className="text-[11px] text-red-300 font-mono whitespace-pre-wrap break-all leading-[1.6]">
                    {detail.stack}
                  </pre>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </section>
      )}

      {/* ── Actions ──────────────────────────────────────────── */}
      <section>
        <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3">Actions</h3>
        <div className="space-y-3">

          {/* Resolve / Reopen */}
          <div className="card p-4">
            <p className="text-[12px] text-surface-700 mb-2">Triage</p>
            {detail.resolved ? (
              <ActionBtn
                icon={XCircle}
                label="Reopen"
                disabled={actionLoading}
                onClick={() => toggleResolve(detail.id, false)}
                color="amber"
              />
            ) : (
              <ActionBtn
                icon={CheckCircle2}
                label="Mark as resolved"
                disabled={actionLoading}
                onClick={() => toggleResolve(detail.id, true)}
                color="green"
              />
            )}
          </div>

          {/* Link to video */}
          <div className="card p-4">
            <p className="text-[12px] text-surface-700 mb-2">Link to video</p>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Video ID"
                value={linkVideoId}
                onChange={(e) => setLinkVideoId(e.target.value)}
                className="flex-1 h-[34px] px-3 rounded-[6px] bg-surface-200 text-[13px] text-white font-mono placeholder:text-surface-600 focus:outline-none focus:ring-1 focus:ring-brand-500/40"
              />
              <ActionBtn
                icon={Link2}
                label="Link"
                disabled={!linkVideoId.trim() || actionLoading}
                onClick={() => linkVideo(detail.id)}
                color="brand"
              />
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}


// ══════════════════════════════════════════════════════════════════════
// Subcomponents
// ══════════════════════════════════════════════════════════════════════

function Row({ label, value, mono = false, children }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[12px] text-surface-600">{label}</span>
      {children || (
        <span className={`text-[13px] text-white ${mono ? 'font-mono text-[11px] text-surface-700' : ''}`}>{String(value)}</span>
      )}
    </div>
  );
}

function ActionBtn({ icon: Icon, label, onClick, disabled = false, color = 'brand' }) {
  const colors = {
    brand: 'bg-brand-500/10 text-brand-400 hover:bg-brand-500/20',
    green: 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20',
    amber: 'bg-amber-500/10 text-amber-400 hover:bg-amber-500/20',
    red: 'bg-red-500/10 text-red-400 hover:bg-red-500/20',
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

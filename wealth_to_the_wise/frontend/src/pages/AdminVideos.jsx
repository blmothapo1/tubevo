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
  Film,
  X,
  ArrowLeft,
  RefreshCw,
  ExternalLink,
  RotateCcw,
  Clock,
  FileText,
  Mic,
  Tag,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Upload,
  CalendarDays,
  User,
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

function formatDuration(secs) {
  if (secs == null) return '—';
  if (secs < 60) return `${Math.round(secs)}s`;
  return `${Math.floor(secs / 60)}m ${Math.round(secs % 60)}s`;
}

const STATUS_CONFIG = {
  pending:    { label: 'Pending',    color: 'text-surface-600', bg: 'bg-surface-300',      icon: Clock },
  generating: { label: 'Generating', color: 'text-brand-400',   bg: 'bg-brand-500/10',     icon: Loader2 },
  completed:  { label: 'Completed',  color: 'text-emerald-400', bg: 'bg-emerald-500/10',   icon: CheckCircle2 },
  posted:     { label: 'Posted',     color: 'text-emerald-400', bg: 'bg-emerald-500/10',   icon: Upload },
  failed:     { label: 'Failed',     color: 'text-red-400',     bg: 'bg-red-500/10',       icon: AlertTriangle },
};

const ALL_STATUSES = ['pending', 'generating', 'completed', 'posted', 'failed'];


// ══════════════════════════════════════════════════════════════════════
// Main page
// ══════════════════════════════════════════════════════════════════════

export default function AdminVideos() {
  const { user: me } = useAuth();
  const navigate = useNavigate();

  // ── List state ──────────────────────────────────────────────────
  const [videos, setVideos] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [totalPages, setTotalPages] = useState(1);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [loading, setLoading] = useState(true);

  // ── Detail state ────────────────────────────────────────────────
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // ── Action state ────────────────────────────────────────────────
  const [retrying, setRetrying] = useState(false);
  const [actionMsg, setActionMsg] = useState(null);

  // ── Fetch video list ────────────────────────────────────────────
  const fetchVideos = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('page', page);
      params.set('page_size', pageSize);
      if (search) params.set('search', search);
      if (statusFilter) params.set('status', statusFilter);
      if (dateFrom) params.set('date_from', new Date(dateFrom).toISOString());
      if (dateTo) params.set('date_to', new Date(dateTo + 'T23:59:59').toISOString());

      const { data } = await api.get(`/api/admin/videos?${params}`);
      setVideos(data.videos);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch {
      // degrade gracefully
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, statusFilter, dateFrom, dateTo]);

  useEffect(() => { fetchVideos(); }, [fetchVideos]);

  // Reset to page 1 when filters change
  useEffect(() => { setPage(1); }, [search, statusFilter, dateFrom, dateTo]);

  // ── Fetch video detail ──────────────────────────────────────────
  const openDetail = async (videoId) => {
    setDetailLoading(true);
    setDetail(null);
    setActionMsg(null);
    try {
      const { data } = await api.get(`/api/admin/videos/${videoId}`);
      setDetail(data);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => { setDetail(null); setActionMsg(null); };

  // ── Retry action ────────────────────────────────────────────────
  const retryVideo = async (videoId) => {
    setRetrying(true);
    setActionMsg(null);
    try {
      const { data } = await api.post(`/api/admin/videos/${videoId}/retry`);
      setActionMsg({ type: 'success', text: data.message });
      // Refresh detail and list
      await openDetail(videoId);
      fetchVideos();
    } catch (err) {
      setActionMsg({ type: 'error', text: err.response?.data?.detail || 'Retry failed.' });
    } finally {
      setRetrying(false);
    }
  };

  // ══════════════════════════════════════════════════════════════════
  // Render
  // ══════════════════════════════════════════════════════════════════

  return (
    <div className="min-h-screen bg-surface-50 flex flex-col">
      {/* ── Top bar ───────────────────────────────────────────────── */}
      <header className="h-[60px] glass sticky top-0 z-20 flex items-center justify-between px-5 sm:px-8 safe-area-inset">
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

      <main className="flex-1 w-full max-w-6xl mx-auto px-6 py-6 sm:px-7 sm:py-8 lg:px-8">

        {/* ── Page title ─────────────────────────────────────────── */}
        <FadeIn>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-[22px] sm:text-[26px] font-semibold text-white tracking-tight flex items-center gap-2">
                <Film size={22} className="text-brand-400" /> Videos
              </h1>
              <p className="text-[12px] text-surface-600 mt-1 uppercase tracking-[0.08em] font-medium">
                {total} total videos
              </p>
            </div>
            <motion.button
              whileHover={{ scale: 1.06 }}
              whileTap={{ scale: 0.94 }}
              onClick={fetchVideos}
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
                placeholder="Search title, topic, or user email…"
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

            {/* Status filter */}
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-[38px] px-3 rounded-[8px] bg-surface-200 text-[13px] text-white focus:outline-none focus:ring-1 focus:ring-brand-500/40 appearance-none cursor-pointer"
            >
              <option value="">All statuses</option>
              {ALL_STATUSES.map((s) => (
                <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
              ))}
            </select>

            {/* Date from */}
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="h-[38px] px-3 rounded-[8px] bg-surface-200 text-[13px] text-white focus:outline-none focus:ring-1 focus:ring-brand-500/40 cursor-pointer"
              title="From date"
            />

            {/* Date to */}
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="h-[38px] px-3 rounded-[8px] bg-surface-200 text-[13px] text-white focus:outline-none focus:ring-1 focus:ring-brand-500/40 cursor-pointer"
              title="To date"
            />

            {/* Clear filters */}
            {(search || statusFilter || dateFrom || dateTo) && (
              <button
                onClick={() => { setSearch(''); setStatusFilter(''); setDateFrom(''); setDateTo(''); }}
                className="h-[38px] px-3 rounded-[8px] text-[12px] font-medium text-surface-600 hover:text-white hover:bg-white/[0.04] transition-colors"
              >
                Clear
              </button>
            )}
          </div>
        </FadeIn>

        {/* ── Table ──────────────────────────────────────────────── */}
        <FadeIn delay={0.1}>
          <div className="card overflow-hidden">
            {/* Header */}
            <div className="hidden lg:grid grid-cols-[1fr_160px_90px_90px_90px_90px] gap-3 px-4 py-2.5 text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] border-b border-white/[0.04]">
              <span>Title / Topic</span>
              <span>User</span>
              <span>Status</span>
              <span>Duration</span>
              <span>YouTube</span>
              <span>Created</span>
            </div>

            {loading ? (
              <div className="p-4 space-y-3">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="flex gap-3 items-center">
                    <div className="skeleton h-4 flex-1" />
                    <div className="skeleton h-4 w-20" />
                    <div className="skeleton h-4 w-16" />
                  </div>
                ))}
              </div>
            ) : videos.length === 0 ? (
              <div className="px-6 py-14 text-center">
                <p className="text-[14px] text-surface-700">No videos found.</p>
              </div>
            ) : (
              <div className="divide-y divide-white/[0.03]">
                {videos.map((v) => {
                  const cfg = STATUS_CONFIG[v.status] || STATUS_CONFIG.pending;
                  const StatusIcon = cfg.icon;
                  return (
                    <motion.div
                      key={v.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      onClick={() => openDetail(v.id)}
                      className="grid grid-cols-1 lg:grid-cols-[1fr_160px_90px_90px_90px_90px] gap-1 lg:gap-3 px-4 py-3 cursor-pointer hover:bg-white/[0.02] transition-colors duration-100"
                    >
                      {/* Title + topic */}
                      <div className="min-w-0">
                        <p className="text-[13px] text-white truncate">{v.title}</p>
                        {v.topic !== v.title && (
                          <p className="text-[11px] text-surface-600 truncate">{v.topic}</p>
                        )}
                        {v.error_message && (
                          <p className="text-[10px] text-red-400 truncate mt-0.5">{v.error_message.slice(0, 80)}</p>
                        )}
                      </div>
                      {/* User email */}
                      <span className="text-[12px] text-surface-700 self-center truncate">{v.user_email || v.user_id?.slice(0, 8)}</span>
                      {/* Status */}
                      <span className={`inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-[5px] ${cfg.color} ${cfg.bg} self-center w-fit`}>
                        <StatusIcon size={11} className={v.status === 'generating' ? 'animate-spin' : ''} />
                        {cfg.label}
                      </span>
                      {/* Processing time */}
                      <span className="text-[12px] text-surface-600 self-center tabular-nums">{formatDuration(v.processing_seconds)}</span>
                      {/* YouTube */}
                      <span className="self-center">
                        {v.youtube_url ? (
                          <a
                            href={v.youtube_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="text-brand-400 hover:text-brand-300"
                          >
                            <ExternalLink size={13} />
                          </a>
                        ) : (
                          <span className="text-[11px] text-surface-600">—</span>
                        )}
                      </span>
                      {/* Created */}
                      <span className="text-[11px] text-surface-600 self-center tabular-nums">{timeSince(v.created_at)}</span>
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
                Page {page} of {totalPages} · {total} videos
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
              className="fixed right-0 top-0 bottom-0 w-full sm:w-[520px] max-w-full bg-surface-100 z-40 flex flex-col overflow-y-auto"
            >
              {/* Header */}
              <div className="sticky top-0 z-10 glass px-5 py-4 flex items-center justify-between">
                <h2 className="text-[16px] font-semibold text-white">Video Detail</h2>
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

                  {/* Action messages */}
                  {actionMsg && (
                    <div className={`px-4 py-2.5 rounded-[8px] text-[13px] font-medium ${actionMsg.type === 'success' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
                      {actionMsg.text}
                    </div>
                  )}

                  {/* ── Overview ────────────────────────────────────── */}
                  <section>
                    <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3">Overview</h3>
                    <div className="card p-4 space-y-2.5">
                      <Row label="ID" value={detail.id} mono />
                      <Row label="Title" value={detail.title} />
                      <Row label="Topic" value={detail.topic} />
                      <Row label="User" value={detail.user_email || detail.user_id} />
                      <Row label="Status" value={detail.status} badge={statusBadgeColor(detail.status)} />
                      <Row label="Progress" value={`${detail.progress_pct}% — ${detail.progress_step || '—'}`} />
                      <Row label="Processing time" value={formatDuration(detail.processing_seconds)} />
                      <Row label="Created" value={fmtDateTime(detail.created_at)} />
                      <Row label="Updated" value={fmtDateTime(detail.updated_at)} />
                      {detail.published_at && <Row label="Published" value={fmtDateTime(detail.published_at)} />}
                    </div>
                  </section>

                  {/* ── YouTube ──────────────────────────────────────── */}
                  {detail.youtube_url && (
                    <section>
                      <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3">YouTube</h3>
                      <div className="card p-4 space-y-2.5">
                        <Row label="Video ID" value={detail.youtube_video_id} mono />
                        <div className="flex items-center justify-between">
                          <span className="text-[12px] text-surface-600">URL</span>
                          <a
                            href={detail.youtube_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[13px] text-brand-400 hover:text-brand-300 inline-flex items-center gap-1"
                          >
                            Open <ExternalLink size={11} />
                          </a>
                        </div>
                      </div>
                    </section>
                  )}

                  {/* ── Metadata (title, description, tags) ─────────── */}
                  {detail.metadata && (
                    <section>
                      <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3 flex items-center gap-1.5">
                        <Tag size={12} /> Metadata
                      </h3>
                      <div className="card p-4 space-y-3">
                        {detail.metadata.title && (
                          <div>
                            <p className="text-[11px] text-surface-600 mb-0.5">Title</p>
                            <p className="text-[13px] text-white">{detail.metadata.title}</p>
                          </div>
                        )}
                        {detail.metadata.description && (
                          <div>
                            <p className="text-[11px] text-surface-600 mb-0.5">Description</p>
                            <p className="text-[12px] text-surface-800 whitespace-pre-wrap leading-relaxed max-h-[200px] overflow-y-auto">{detail.metadata.description}</p>
                          </div>
                        )}
                        {detail.metadata.tags && detail.metadata.tags.length > 0 && (
                          <div>
                            <p className="text-[11px] text-surface-600 mb-1">Tags</p>
                            <div className="flex flex-wrap gap-1.5">
                              {detail.metadata.tags.map((tag, i) => (
                                <span key={i} className="text-[11px] px-2 py-0.5 rounded-[5px] bg-surface-300 text-surface-700">{tag}</span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </section>
                  )}

                  {/* ── Voice ─────────────────────────────────────────── */}
                  {detail.voice_id && (
                    <section>
                      <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3 flex items-center gap-1.5">
                        <Mic size={12} /> Voice
                      </h3>
                      <div className="card p-4">
                        <Row label="Voice ID" value={detail.voice_id} mono />
                      </div>
                    </section>
                  )}

                  {/* ── Script ────────────────────────────────────────── */}
                  {detail.script_text && (
                    <section>
                      <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3 flex items-center gap-1.5">
                        <FileText size={12} /> Script
                      </h3>
                      <div className="card p-4">
                        <pre className="text-[12px] text-surface-800 whitespace-pre-wrap leading-relaxed max-h-[300px] overflow-y-auto font-sans">
                          {detail.script_text}
                        </pre>
                      </div>
                    </section>
                  )}

                  {/* ── Pipeline Log ──────────────────────────────────── */}
                  {detail.pipeline_log && detail.pipeline_log.length > 0 && (
                    <section>
                      <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3 flex items-center gap-1.5">
                        <Clock size={12} /> Pipeline Steps ({detail.pipeline_log.length})
                      </h3>
                      <div className="card overflow-hidden divide-y divide-white/[0.03]">
                        {detail.pipeline_log.map((step, i) => {
                          const prev = i > 0 ? detail.pipeline_log[i - 1] : null;
                          const elapsed = prev && step.ts && prev.ts ? (step.ts - prev.ts).toFixed(1) : null;
                          return (
                            <div key={i} className="px-4 py-2.5 flex items-center gap-3">
                              <div className="w-7 h-7 rounded-[6px] bg-brand-500/10 flex items-center justify-center shrink-0">
                                <span className="text-[10px] font-bold text-brand-400 tabular-nums">{step.pct}%</span>
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-[13px] text-surface-800 truncate">{step.step}</p>
                              </div>
                              {elapsed && (
                                <span className="text-[10px] text-surface-600 tabular-nums shrink-0">+{elapsed}s</span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </section>
                  )}

                  {/* ── Error Details ─────────────────────────────────── */}
                  {detail.error_message && (
                    <section>
                      <h3 className="text-[11px] text-red-400 font-medium uppercase tracking-[0.08em] mb-3 flex items-center gap-1.5">
                        <AlertTriangle size={12} /> Error Details
                      </h3>
                      <div className="card p-4 border-l-[3px] border-l-red-500">
                        <pre className="text-[12px] text-red-400 whitespace-pre-wrap leading-relaxed max-h-[200px] overflow-y-auto font-mono">
                          {detail.error_message}
                        </pre>
                      </div>
                    </section>
                  )}

                  {/* ── Admin Actions ─────────────────────────────────── */}
                  {detail.status === 'failed' && (
                    <section>
                      <h3 className="text-[11px] text-surface-600 font-medium uppercase tracking-[0.08em] mb-3">Actions</h3>
                      <div className="card p-4">
                        <p className="text-[12px] text-surface-700 mb-2">Re-run the pipeline for this failed video with the same topic and user keys.</p>
                        <motion.button
                          whileHover={{ scale: retrying ? 1 : 1.01 }}
                          whileTap={{ scale: retrying ? 1 : 0.97 }}
                          onClick={() => retryVideo(detail.id)}
                          disabled={retrying}
                          className="inline-flex items-center gap-1.5 px-3.5 h-[34px] rounded-[8px] bg-amber-500/10 text-amber-400 text-[12px] font-medium hover:bg-amber-500/20 transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <RotateCcw size={13} className={retrying ? 'animate-spin' : ''} />
                          {retrying ? 'Retrying…' : 'Retry Video'}
                        </motion.button>
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

function statusBadgeColor(status) {
  if (status === 'completed' || status === 'posted') return 'green';
  if (status === 'failed') return 'red';
  if (status === 'generating') return 'brand';
  return 'surface';
}

function Row({ label, value, mono = false, badge = null }) {
  const badgeColors = {
    brand: 'text-brand-400 bg-brand-500/10',
    surface: 'text-surface-700 bg-surface-300',
    green: 'text-emerald-400 bg-emerald-500/10',
    red: 'text-red-400 bg-red-500/10',
    amber: 'text-amber-400 bg-amber-500/10',
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
